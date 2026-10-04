local current = redis.call("INCR", KEYS[1])
local pttl = redis.call("PTTL", KEYS[1])

if current == 1 or pttl < 0 then
    pttl = tonumber(ARGV[1]) * 1000
    redis.call("PEXPIRE", KEYS[1], pttl)
end

return {current, math.ceil(pttl / 1000)}