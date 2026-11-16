-- Nova Hub (Luna Interface Suite)
-- Layout: catalog/index.json has one row per game, catalog/games/<placeId>.json
-- holds that game's scripts. Hub pulls only what it needs and caches both.

local CATALOG_BASE = "https://raw.githubusercontent.com/Siidodirnfb/Nova-Hub/main/catalog"
local INDEX_TTL = 3600 -- seconds a cached index stays fresh

local Luna = loadstring(game:HttpGet("https://raw.githubusercontent.com/Nebula-Softworks/Luna-Interface-Suite/refs/heads/master/source.lua", true))()
local HttpService = game:GetService("HttpService")

local function notify(title, content)
	Luna:Notification({ Title = title, Icon = "info", ImageSource = "Material", Content = content })
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
	local cached = readJSON("NovaHub/index.json")
	if cached and cached.generated and (os.time() - cached.generated) < INDEX_TTL and cached.games then
		return cached
	end
	local data, raw = fetchJSON(CATALOG_BASE .. "/index.json")
	if data and data.games then
		writeJSON("NovaHub/index.json", raw)
		return data
	end
	return cached
end

local index = loadIndex()
local placeId = tostring(game.PlaceId)

local function loadGame(id)
	local cached = readJSON("NovaHub/games/" .. id .. ".json")
	if cached and (cached.noKey or cached.key) then
		return cached
	end
	local data, raw = fetchJSON(CATALOG_BASE .. "/games/" .. id .. ".json")
	if data then
		writeJSON("NovaHub/games/" .. id .. ".json", raw)
		return data
	end
	return cached
end

local catalogCount = index and index.count or 0

local Window = Luna:CreateWindow({
	Name = "Nova Hub",
	Subtitle = catalogCount .. " games catalogued",
	LogoID = nil,
	LoadingEnabled = true,
	LoadingTitle = "Nova Hub",
	LoadingSubtitle = "loading catalog",
	ConfigSettings = {
		RootFolder = nil,
		ConfigFolder = "Nova Hub"
	},
	KeySystem = false
})

Window:CreateHomeTab({
	SupportedExecutors = { "Wave", "Delta", "Codex", "Matcha", "Volt", "Potassium", "OpiumWare" },
	DiscordInvite = "nova",
	Icon = 1
})

local function runScript(item)
	local ok, err = pcall(function()
		if not item.rawScript then
			error("this entry has no script url")
		end
		local src = game:HttpGet(item.rawScript, true)
		loadstring(src)()
	end)
	if ok then
		notify("Started", item.title or "script")
	else
		notify("Script failed", tostring(err):sub(1, 180))
	end
end

local function addScripts(tab, list, emptyText)
	if not list or #list == 0 then
		tab:CreateLabel({ Text = emptyText, Style = 2 })
		return
	end
	for _, item in ipairs(list) do
		tab:CreateButton({
			Name = item.title or "Unnamed script",
			Description = string.format("%s views, %s likes", tostring(item.views or 0), tostring(item.likes or 0)),
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
		Text = string.format("%splaceId %s, %d script%s without a key, %d with a key.",
			isCurrent and "You are in this game. " or "",
			id, #(entry.noKey or {}), (#(entry.noKey or {}) == 1 and "" or "s"), #(entry.key or {}))
	})
	tab:CreateLabel({ Text = "No key", Style = 1 })
	addScripts(tab, entry.noKey, "No keyless scripts for this game yet.")
	tab:CreateLabel({ Text = "With key", Style = 1 })
	addScripts(tab, entry.key, "No key-locked scripts for this game yet.")
	return tab
end

-- current game ------------------------------------------------------------
local currentRow = index and index.games and index.games[placeId] or nil
local InfoTab = Window:CreateTab({
	Name = "Game",
	Icon = "my_location",
	ImageSource = "Material",
	ShowTitle = true
})

if currentRow then
	InfoTab:CreateParagraph({
		Title = currentRow.name or ("place " .. placeId),
		Text = "Loading scripts for this game..."
	})
	local entry = loadGame(placeId) or { name = currentRow.name, noKey = {}, key = {} }
	InfoTab:CreateLabel({ Text = "No key", Style = 1 })
	addScripts(InfoTab, entry.noKey, "No keyless scripts for this game yet.")
	InfoTab:CreateLabel({ Text = "With key", Style = 1 })
	addScripts(InfoTab, entry.key, "No key-locked scripts for this game yet.")
else
	InfoTab:CreateParagraph({
		Title = "Not catalogued",
		Text = string.format("PlaceId %s is not in the catalog. Use the Catalog tab to browse the %d games that are.",
			placeId, catalogCount)
	})
end

-- catalog browser --------------------------------------------------------
local SearchTab = Window:CreateTab({
	Name = "Catalog",
	Icon = "search",
	ImageSource = "Material",
	ShowTitle = true
})

SearchTab:CreateParagraph({
	Title = "Browse the catalog",
	Text = string.format("%d games. Type part of a name and press Enter to search.", catalogCount)
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
	Description = "Press Enter to search",
	PlaceholderText = "blox fruits",
	MaxCharacters = 40,
	Enter = true,
	Callback = function(text)
		local matches = searchCatalog(text)
		if #matches == 0 then
			SearchTab:CreateLabel({ Text = "Nothing matches \"" .. text .. "\"", Style = 3 })
			return
		end
		SearchTab:CreateDivider()
		SearchTab:CreateLabel({ Text = #matches .. " matches for \"" .. text .. "\"", Style = 2 })
		for i = 1, math.min(#matches, 6) do
			local m = matches[i]
			SearchTab:CreateButton({
				Name = m.row.name,
				Description = string.format("placeId %s, %d without key, %d with key", m.id, m.row.nk or 0, m.row.k or 0),
				Callback = function()
					local entry = loadGame(m.id)
					if not entry then
						notify("Unavailable", "Could not download scripts for " .. (m.row.name or m.id))
						return
					end
					openGameTab(entry, m.id, m.id == placeId)
				end
			})
		end
	end
})
