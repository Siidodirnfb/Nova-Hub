-- Vesper (Luna Interface Suite)
-- Reads catalog/index.json for the game list and catalog/games/<placeId>.json
-- for that game's scripts. Both are cached locally for an hour.
--
-- The hub only performs HTTP GET requests, to the catalog host and to the
-- script links that live inside the catalog. It never posts data anywhere and
-- writes nothing outside its own cache folder.

local CATALOG_BASE = "https://raw.githubusercontent.com/Siidodirnfb/Vesper-Hub/main/catalog"
local SOURCE_URL = "https://github.com/Siidodirnfb/Vesper-Hub"
local BUILD = "vesper-2026-11-16"
local INDEX_TTL = 3600

local Luna = loadstring(game:HttpGet("https://raw.githubusercontent.com/Nebula-Softworks/Luna-Interface-Suite/refs/heads/master/source.lua", true))()
local HttpService = game:GetService("HttpService")

-- provenance marker: a copy without this string did not come from us
getgenv().Vesper = { build = BUILD, source = SOURCE_URL }

local function notify(title, content)
	Luna:Notification({ Title = title, Icon = "info", ImageSource = "Material", Content = content })
end

local function fmt(n)
	local s = tostring(math.floor(tonumber(n) or 0))
	local out = s:reverse():gsub("(%d%d%d)", "%1,"):reverse()
	return (out:gsub("^,", ""))
end

local function ensureFolder(path)
	if makefolder then
		pcall(makefolder, path)
	end
end

local function readJSON(path)
	if not (isfile and isfile(path)) then
		return nil
	end
	local ok, raw = pcall(readfile, path)
	if not ok or not raw then
		return nil
	end
	local ok2, data = pcall(function()
		return HttpService:JSONDecode(raw)
	end)
	return ok2 and data or nil
end

local function writeJSON(path, raw)
	if not (writefile and isfile) then
		return
	end
	local folder = path:match("^(.-)/[^/]+$")
	if folder then
		ensureFolder(folder)
	end
	pcall(writefile, path, raw)
end

local function fetchJSON(url)
	local ok, raw = pcall(game.HttpGet, game, url, true)
	if not ok or not raw or raw == "" then
		return nil
	end
	local ok2, data = pcall(function()
		return HttpService:JSONDecode(raw)
	end)
	if not ok2 then
		return nil
	end
	return data, raw
end

local function loadIndex()
	local cached = readJSON("Vesper/index.json")
	if cached and cached.generated and (os.time() - cached.generated) < INDEX_TTL and cached.games then
		return cached
	end
	local data, raw = fetchJSON(CATALOG_BASE .. "/index.json")
	if data and data.games then
		writeJSON("Vesper/index.json", raw)
		return data
	end
	return cached
end

local index = loadIndex()
local placeId = tostring(game.PlaceId)

local function loadGame(id)
	local cached = readJSON("Vesper/games/" .. id .. ".json")
	if cached and (cached.noKey or cached.key) then
		return cached
	end
	local data, raw = fetchJSON(CATALOG_BASE .. "/games/" .. id .. ".json")
	if data then
		writeJSON("Vesper/games/" .. id .. ".json", raw)
		return data
	end
	return cached
end

local catalogCount = index and index.count or 0

local Window = Luna:CreateWindow({
	Name = "Vesper",
	Subtitle = catalogCount ..
		" games, links checked against source",
	LogoID = nil,
	LoadingEnabled = true,
	LoadingTitle = "Vesper",
	LoadingSubtitle = "reading the catalog",
	ConfigSettings = {
		RootFolder = nil,
		ConfigFolder = "Vesper"
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

local function openGameTab(entry, id, isCurrent)
	local tab = Window:CreateTab({
		Name = (entry.name or ("place " .. id)):sub(1, 20),
		Icon = "sports_esports",
		ImageSource = "Material",
		ShowTitle = true
	})
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
	return tab
end

-- the game the player is in ----------------------------------------------
local currentRow = index and index.games and index.games[placeId] or nil
local InfoTab = Window:CreateTab({
	Name = "Game",
	Icon = "my_location",
	ImageSource = "Material",
	ShowTitle = true
})

if currentRow then
	local entry = loadGame(placeId) or { name = currentRow.name, noKey = {}, key = {} }
	InfoTab:CreateParagraph({
		Title = currentRow.name or ("place " .. placeId),
		Text = string.format("placeId %s. %d keyless, %d key-locked.",
			placeId, #(entry.noKey or {}), #(entry.key or {}))
	})
	InfoTab:CreateLabel({ Text = "Keyless", Style = 1 })
	addScripts(InfoTab, entry.noKey, "No keyless scripts for this game.")
	InfoTab:CreateLabel({ Text = "Key-locked", Style = 1 })
	addScripts(InfoTab, entry.key, "No key-locked scripts for this game.")
else
	InfoTab:CreateParagraph({
		Title = "Not indexed",
		Text = string.format("placeId %s has no entry. %d games are indexed in the Catalog tab.", placeId, catalogCount)
	})
end

-- catalog browser ---------------------------------------------------------
local SearchTab = Window:CreateTab({
	Name = "Catalog",
	Icon = "search",
	ImageSource = "Material",
	ShowTitle = true
})

SearchTab:CreateParagraph({
	Title = string.format("%d games indexed", catalogCount),
	Text = "Search a game name, then open its scripts from the result."
})

local function normalize(s)
	return (s or ""):lower():gsub("[^%w%s]", " "):gsub("%s+", " ")
end

local function searchCatalog(query)
	local q = normalize(query):gsub("^%s+", ""):gsub("%s+$", "")
	if #q < 2 or not (index and index.games) then
		return {}
	end
	local scored = {}
	for id, row in pairs(index.games) do
		local name = normalize(row.name)
		local first = name:find(q, 1, true)
		if first then
			scored[#scored + 1] = { id = id, row = row, score = first * 1000 + #name }
		end
	end
	table.sort(scored, function(a, b)
		return a.score < b.score
	end)
	return scored
end

SearchTab:CreateInput({
	Name = "Search",
	PlaceholderText = "blox fruits",
	MaxCharacters = 40,
	Enter = true,
	Callback = function(text)
		local matches = searchCatalog(text)
		if #matches == 0 then
			SearchTab:CreateLabel({ Text = "No game matches \"" .. text .. "\"", Style = 3 })
			return
		end
		SearchTab:CreateDivider()
		SearchTab:CreateLabel({ Text = #matches .. " games match \"" .. text .. "\"", Style = 2 })
		for i = 1, math.min(#matches, 6) do
			local m = matches[i]
			SearchTab:CreateButton({
				Name = m.row.name,
				Description = string.format("placeId %s, %d keyless, %d key-locked", m.id, m.row.nk or 0, m.row.k or 0),
				Callback = function()
					local entry = loadGame(m.id)
					if not entry then
						notify("Not downloaded", "No script file for " .. (m.row.name or m.id))
						return
					end
					openGameTab(entry, m.id, m.id == placeId)
				end
			})
		end
	end
})

SearchTab:CreateDivider()
SearchTab:CreateLabel({ Text = "build " .. BUILD .. ", source at " .. SOURCE_URL, Style = 2 })
