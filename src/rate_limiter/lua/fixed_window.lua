local limit   = tonumber(ARGV[1])
local window  = tonumber(ARGV[2])
local cost    = tonumber(ARGV[3])
local consume = ARGV[4] == "1"

local current = tonumber(redis.call("GET", KEYS[1]) or "0")
local pttl = redis.call("PTTL", KEYS[1])

local allowed = 0
if current + cost <= limit then
    allowed = 1
    if consume then
        current = redis.call("INCRBY", KEYS[1], cost)
    end
end

if consume and current > 0 and pttl < 0 then
    pttl = window * 1000
    redis.call("PEXPIRE", KEYS[1], pttl)
end
if pttl < 0 then
    pttl = 0
end

return {allowed, current, math.ceil(pttl / 1000)}