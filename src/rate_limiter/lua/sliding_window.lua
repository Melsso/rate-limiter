local limit   = tonumber(ARGV[1])
local window  = tonumber(ARGV[2])
local cost    = tonumber(ARGV[3])
local consume = ARGV[4] == "1"

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
if estimated + cost <= limit then
    allowed = 1
    if consume then
        c = c + cost
        estimated = estimated + cost
    end
end

if consume then
    redis.call("HSET", KEYS[1], "w", w, "c", c, "p", p)
    redis.call("EXPIRE", KEYS[1], window * 2)
end

local retry = math.ceil(window - elapsed)
if allowed == 0 then
    if cost > limit then
        retry = window
    else
        local room = limit - c - cost
        if room >= 0 and p > 0 then
            retry = (window - room * window / p) - elapsed
        elseif c > 0 then
            retry = (window - elapsed) + window * (1 - (limit - cost) / c)
        end
        retry = math.ceil(retry)
    end
end
if retry < 1 then retry = 1 end

return {allowed, math.max(0, math.floor(limit - estimated)), retry}