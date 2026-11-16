-- Vesper (Luna Interface Suite)
-- Reads catalog/index.json for the game list and catalog/games/<placeId>.json
-- for that game's scripts. Both are cached locally for six hours.
--
-- Startup does not wait for the network: the window opens, then the catalog is
-- fetched in the background and the tabs fill in when it arrives. Hosts are
-- tried in order, the fastest one is remembered, so a second launch goes
-- straight to the host that answered last time.
--
-- The hub only performs HTTP GET requests, to the catalog host and to the
-- script links that live inside the catalog. It never posts data anywhere and
-- writes nothing outside its own cache folder.

local BUILD = "vesper-2026-11-16"
local SOURCE_URL = "https://github.com/Siidodirnfb/Vesper-Hub"

-- mirrors, direct first. jsDelivr and githack are plain CDNs for the same
-- repository, not proxies: nothing is rewritten, the bytes are identical.
local HOSTS = {
	"https://raw.githubusercontent.com/Siidodirnfb/Vesper-Hub/main/",
	"https://cdn.jsdelivr.net/gh/Siidodirnfb/Vesper-Hub@main/",
	"https://raw.githack.com/Siidodirnfb/Vesper-Hub/main/",
}
local INDEX_TTL = 21600
local CACHE = "Vesper"

local LUNA_URL = "https://raw.githubusercontent.com/Nebula-Softworks/Luna-Interface-Suite/refs/heads/master/source.lua"

getgenv().Vesper = { build = BUILD, source = SOURCE_URL }

local function readText(path)
	if not (isfile and isfile(path)) then
		return nil
	end
	local ok, raw = pcall(readfile, path)
	if ok and type(raw) == "string" and raw ~= "" then
		return raw
	end
	return nil
end

local function writeText(path, raw)
	if not (writefile and type(raw) == "string") then
		return
	end
	local folder = path:match("^(.-)/[^/]+$")
	if folder and makefolder then
		pcall(makefolder, folder)
	end
	pcall(writefile, path, raw)
end

-- pick up the host that answered last time, if any
local hostIndex = tonumber(readText(CACHE .. "/host") or "") or 1
if not HOSTS[hostIndex] then
	hostIndex = 1
end

local function httpGet(path)
	local order = { hostIndex }
	for i = 1, #HOSTS do
		if i ~= hostIndex then
			order[#order + 1] = i
		end
	end
	local err
	for _, i in ipairs(order) do
		local ok, body = pcall(game.HttpGet, game, HOSTS[i] .. path)
		if ok and type(body) == "string" and #body > 0 then
			if i ~= hostIndex then
				hostIndex = i
				writeText(CACHE .. "/host", tostring(i))
			end
			return body
		end
		err = body
	end
	return nil, err
end

local Luna
do
	local ok, body = pcall(game.HttpGet, game, LUNA_URL)
	if not ok or type(body) ~= "string" or #body == 0 then
		error("Vesper: could not download Luna Interface Suite")
	end
	Luna = loadstring(body)()
end

local HttpService = game:GetService("HttpService")

local function decode(raw)
	if not raw then
		return nil
	end
	local ok, data = pcall(function()
		return HttpService:JSONDecode(raw)
	end)
	return ok and data or nil
end

local function notify(title, content)
	Luna:Notification({ Title = title, Icon = "info", ImageSource = "Material", Content = content })
end

local function fmt(n)
	local s = tostring(math.floor(tonumber(n) or 0))
	local out = s:reverse():gsub("(%d%d%d)", "%1,"):reverse()
	return (out:gsub("^,", ""))
end

local index
local indexReady = false

local function loadIndex()
	local cached = decode(readText(CACHE .. "/index.json"))
	if cached and cached.games and (os.time() - (cached.generated or 0)) < INDEX_TTL then
		return cached
	end
	local raw = httpGet("catalog/index.json")
	local data = decode(raw)
	if data and data.games then
		writeText(CACHE .. "/index.json", raw)
		return data
	end
	return cached
end

local function loadGame(id)
	local path = CACHE .. "/games/" .. id .. ".json"
	local cached = decode(readText(path))
	if cached and (cached.noKey or cached.key) and cached.build == BUILD then
		return cached
	end
	local raw = httpGet("catalog/games/" .. id .. ".json")
	local data = decode(raw)
	if data then
		if not data.build then
			data.build = BUILD
		end
		writeText(path, raw)
		return data
	end
	return cached
end

local function runAsync(fn)
	if task and task.spawn then
		task.spawn(fn)
	else
		coroutine.wrap(fn)()
	end
end

local placeId = tostring(game.PlaceId)

local Window = Luna:CreateWindow({
	Name = "Vesper",
	Subtitle = "keyless and key-locked scripts, links checked at build time",
	LogoID = nil,
	LoadingEnabled = true,
	LoadingTitle = "Vesper",
	LoadingSubtitle = "starting",
	ConfigSettings = {
		RootFolder = nil,
		ConfigFolder = CACHE
	},
	KeySystem = false
})

local function runScript(item)
	local ok, err = pcall(function()
		if not item.rawScript then
			error("entry has no script url")
		end
		local src = game:HttpGet(item.rawScript, true)
		loadstring(src)()
	end)
	if ok then
		notify("Running", item.title or "script")
	else
		notify("Did not run", tostring(err):sub(1, 180))
	end
end

local function addScripts(tab, list, emptyText)
	if not list or #list == 0 then
		tab:CreateLabel({ Text = emptyText, Style = 2 })
		return
	end
	for _, item in ipairs(list) do
		local meta = fmt(item.views) .. " views"
		if item.likes and item.likes > 0 then
			meta = meta .. ", " .. fmt(item.likes) .. " likes"
		end
		tab:CreateButton({
			Name = item.title or "Untitled",
			Description = meta,
			Callback = function()
				runScript(item)
			end
		})
	end
end

local function fillGameTab(tab, entry, id, isCurrent)
	tab:CreateParagraph({
		Title = entry.name or ("place " .. id),
		Text = string.format("%splaceId %s. %d keyless, %d key-locked.",
			isCurrent and "The game you are in. " or "",
			id, #(entry.noKey or {}), #(entry.key or {}))
	})
	tab:CreateLabel({ Text = "Keyless", Style = 1 })
	addScripts(tab, entry.noKey, "No keyless scripts for this game.")
	tab:CreateLabel({ Text = "Key-locked", Style = 1 })
	addScripts(tab, entry.key, "No key-locked scripts for this game.")
end

local InfoTab = Window:CreateTab({
	Name = "Game",
	Icon = "my_location",
	ImageSource = "Material",
	ShowTitle = true
})

local SearchTab = Window:CreateTab({
	Name = "Catalog",
	Icon = "search",
	ImageSource = "Material",
	ShowTitle = true
})

SearchTab:CreateInput({
	Name = "Search",
	PlaceholderText = "blox fruits",
	MaxCharacters = 40,
	Enter = true,
	Callback = function(text)
		if not indexReady then
			notify("Catalog still loading", "Try the same search again in a moment.")
			return
		end
		local q = (text or ""):lower():gsub("[^%w%s]", " "):gsub("%s+", " "):gsub("^%s+", ""):gsub("%s+$", "")
		if #q < 2 or not index.games then
			return
		end
		local scored = {}
		for id, row in pairs(index.games) do
			local name = (row.name or ""):lower():gsub("[^%w%s]", " "):gsub("%s+", " ")
			local first = name:find(q, 1, true)
			if first then
				scored[#scored + 1] = { id = id, row = row, score = first * 1000 + #name }
			end
		end
		table.sort(scored, function(a, b)
			return a.score < b.score
		end)
		SearchTab:CreateDivider()
		if #scored == 0 then
			SearchTab:CreateLabel({ Text = "No game matches \"" .. text .. "\"", Style = 3 })
			return
		end
		SearchTab:CreateLabel({ Text = #scored .. " games match \"" .. text .. "\"", Style = 2 })
		for i = 1, math.min(#scored, 6) do
			local m = scored[i]
			SearchTab:CreateButton({
				Name = m.row.name,
				Description = string.format("placeId %s, %d keyless, %d key-locked", m.id, m.row.nk or 0, m.row.k or 0),
				Callback = function()
					local entry = loadGame(m.id)
					if not entry then
						notify("Not downloaded", "No script file for " .. (m.row.name or m.id))
						return
					end
					local tab = Window:CreateTab({
						Name = (entry.name or ("place " .. m.id)):sub(1, 20),
						Icon = "sports_esports",
						ImageSource = "Material",
						ShowTitle = true
					})
					fillGameTab(tab, entry, m.id, m.id == placeId)
				end
			})
		end
	end
})

SearchTab:CreateDivider()
SearchTab:CreateLabel({ Text = "build " .. BUILD .. ", source at " .. SOURCE_URL, Style = 2 })

-- background: the window is already on screen, this only fills the tabs
runAsync(function()
	local ok, err = pcall(function()
		index = loadIndex()
		indexReady = index ~= nil and index.games ~= nil
		if not indexReady then
			InfoTab:CreateParagraph({
				Title = "Catalog unavailable",
				Text = "The index did not download. Check the connection and run the hub again."
			})
			return
		end
		local row = index.games[placeId]
		if row then
			local entry = loadGame(placeId) or { name = row.name, noKey = {}, key = {} }
			fillGameTab(InfoTab, entry, placeId, true)
		else
			InfoTab:CreateParagraph({
				Title = "Not indexed",
				Text = string.format("placeId %s has no entry. %d games are in the Catalog tab.", placeId, index.count or 0)
			})
		end
		SearchTab:CreateDivider()
		SearchTab:CreateLabel({ Text = fmt(index.count or 0) .. " games indexed", Style = 2 })
	end)
	if not ok then
		notify("Catalog unavailable", tostring(err):sub(1, 180))
	end
end)
