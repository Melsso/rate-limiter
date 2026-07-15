local tokens = tonumber(redis.call("GET", KEYS[1]))
local last_time = tonumber(redis.call("GET", KEYS[2]))

local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

if tokens == nil then
    tokens = capacity
end

if last_time == nil then
    last_time = now
end

local elapsed = now - last_time

tokens = math.min(
    capacity,
    tokens + (elapsed * refill_rate)
)

local allowed = 0

if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end

local ttl = math.ceil(capacity / refill_rate) + 60

redis.call("SET", KEYS[1], tokens, "EX", ttl)
redis.call("SET", KEYS[2], now, "EX", ttl)

return {
    allowed,
    math.floor(tokens),
    math.floor((capacity - tokens) / refill_rate)
}