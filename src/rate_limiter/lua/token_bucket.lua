local capacity = tonumber(ARGV[1])
local rate     = tonumber(ARGV[2])

local t = redis.call("TIME")
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000

local d = redis.call("HMGET", KEYS[1], "tokens", "ts")
local tokens, ts = tonumber(d[1]), tonumber(d[2])
if tokens == nil or ts == nil then
    tokens, ts = capacity, now
end

tokens = math.min(capacity, tokens + math.max(0, now - ts) * rate)

local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end

redis.call("HSET", KEYS[1], "tokens", tokens, "ts", now)
redis.call("EXPIRE", KEYS[1], math.ceil(capacity / rate) + 1)

local reset
if allowed == 1 then
    reset = math.ceil((capacity - tokens) / rate)
else
    reset = math.ceil((1 - tokens) / rate)
end

return {allowed, math.floor(tokens), reset}