local capacity = tonumber(ARGV[1])
local rate     = tonumber(ARGV[2])
local cost     = tonumber(ARGV[3])
local consume  = ARGV[4] == "1"

local t = redis.call("TIME")
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000

local d = redis.call("HMGET", KEYS[1], "tokens", "ts")
local tokens, ts = tonumber(d[1]), tonumber(d[2])
if tokens == nil or ts == nil then
    tokens, ts = capacity, now
end

tokens = math.min(capacity, tokens + math.max(0, now - ts) * rate)

local allowed = 0
if tokens >= cost then
    allowed = 1
    if consume then
        tokens = tokens - cost
    end
end

if consume then
    redis.call("HSET", KEYS[1], "tokens", tokens, "ts", now)
    redis.call("EXPIRE", KEYS[1], math.ceil(capacity / rate) + 1)
end

local reset
if allowed == 1 then
    reset = math.ceil((capacity - tokens) / rate)
else
    reset = math.ceil((cost - tokens) / rate)
end

return {allowed, math.floor(tokens), reset}