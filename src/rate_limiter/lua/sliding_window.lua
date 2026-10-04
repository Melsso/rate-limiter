local limit  = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

local t = redis.call("TIME")
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local idx = math.floor(now / window)
local elapsed = now - idx * window

local d = redis.call("HMGET", KEYS[1], "w", "c", "p")
local w = tonumber(d[1])
local c = tonumber(d[2]) or 0
local p = tonumber(d[3]) or 0

if w == nil or idx > w + 1 then
    w, c, p = idx, 0, 0
elseif idx == w + 1 then
    w, c, p = idx, 0, c
end

local weight = (window - elapsed) / window
local estimated = p * weight + c

local allowed = 0
if estimated + 1 <= limit then
    c = c + 1
    estimated = estimated + 1
    allowed = 1
end

redis.call("HSET", KEYS[1], "w", w, "c", c, "p", p)
redis.call("EXPIRE", KEYS[1], window * 2)

local retry = math.ceil(window - elapsed)
if allowed == 0 then
    local room = limit - c - 1
    if room >= 0 and p > 0 then
        retry = (window - room * window / p) - elapsed
    elseif c > 0 then
        retry = (window - elapsed) + window * (1 - (limit - 1) / c)
    end
    retry = math.ceil(retry)
end
if retry < 1 then retry = 1 end

return {allowed, math.max(0, math.floor(limit - estimated)), retry}