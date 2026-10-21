-- Character create laid out as Battle for Azeroth's (retroport glue package, `retroport glue`):
-- a gender box with the Alliance and Horde race columns hanging from it on their banners (races
-- 3.3.5 never shipped on an "Allied Races" page of their own), a class column down the right
-- edge, race and class info panels behind "More Info", then a customization step on a faction
-- banner. The character stands in BfA's faction scene (UI_Alliance / UI_Horde). Everything runs
-- on the 3.3.5a glue API; race packages add their icons below (RACE_ICON_TCOORDS) and their text
-- to GlueStrings.lua.
RETROPORT_GLUE_STYLE = "bfa";

CHARACTER_FACING_INCREMENT = 2;
MAX_RACES = 32;
MAX_CLASSES_PER_RACE = 10;
NUM_CHAR_CUSTOMIZATIONS = 5;
-- the x64 client (WarcraftXL's native retail characters) offers a race's retail options instead:
-- this many rows of them to a page, the banner growing by a row's height for each past five
CHARCREATE_CUSTOMIZATION_ROWS = 9;
CHARCREATE_CUSTOMIZATION_ROW_HEIGHT = 46;
CHARCREATE_CUSTOMIZATION_BANNER = 210;
MIN_CHAR_NAME_LENGTH = 2;
CHARACTER_CREATE_ROTATION_START_X = nil;
CHARACTER_CREATE_INITIAL_FACING = nil;

PAID_CHARACTER_CUSTOMIZATION = 1;
PAID_RACE_CHANGE = 2;
PAID_FACTION_CHANGE = 3;
PAID_SERVICE_CHARACTER_ID = nil;
PAID_SERVICE_TYPE = nil;

-- BfA's strings 3.3.5 lacks
CUSTOMIZE = CUSTOMIZE or "Customize";
FINISH = FINISH or "Finish";
CHARACTER_CREATE_MORE_RACES = CHARACTER_CREATE_MORE_RACES or "Allied Races";
CHARACTER_CREATE_CORE_RACES = CHARACTER_CREATE_CORE_RACES or "Core Races";
CHAR_CREATE_MORE_INFO = CHAR_CREATE_MORE_INFO or "More Info";
CHAR_CREATE_LESS_INFO = CHAR_CREATE_LESS_INFO or "Less Info";
CUSTOMIZE_OPTIONS = CUSTOMIZE_OPTIONS or "Customize";

CHARCREATE_RACE_TOP = -139;      -- the first race button, from the top of the gender box (BfA's
                                 -- 50-unit buttons start at -136; ours, 44, sit on their middle)
CHARCREATE_RACE_ROW = 70;        -- a race button and its name (BfA: 50 + 20)
CHARCREATE_RACE_COLUMN = 43;     -- each faction's column, either side of the box's middle
CHARCREATE_BANNER_HEIGHT, CHARCREATE_BANNER_ROWS = 478, 6;   -- BfA's banners: six races a side
CHARCREATE_BANNER_MIN_ROWS = 5;  -- drawn as long as the page's races need, five at least
CHARCREATE_CLASS_TOP = -8;       -- the first class button, under the column's title (BfA: 8)
CHARCREATE_CLASS_ROW = 55;       -- a class button and its name (BfA: 40 + 15)
CHARCREATE_INFO_MIN, CHARCREATE_INFO_MAX = 250, 550;

-- the races 3.3.5 shipped; any other is an allied race, on BfA's "Allied Races" page
CHARCREATE_CORE_RACES = {
	HUMAN = true, DWARF = true, NIGHTELF = true, GNOME = true, DRAENEI = true,
	ORC = true, SCOURGE = true, TAUREN = true, TROLL = true, BLOODELF = true,
};
-- the scene each faction creates in: Interface\Glues\Models\UI_<scene>\UI_<scene>.m2
CHARCREATE_FACTION_SCENES = { Alliance = "Alliance", Horde = "Horde" };
-- the customize zoom: CHARCREATE_ZOOM, the cameras the glue build added to those scenes, and
-- each race's head (RACE_SEX -> { yards up, yards forward of the feet }) - the build's for the
-- races 3.3.5 shipped, a race package's for its own (both at the end of this file)
CHARCREATE_ZOOM_HEAD = CHARCREATE_ZOOM_HEAD or {};
CHARCREATE_ZOOM_WIDE = CHARCREATE_ZOOM_WIDE or {};      -- RACE_SEX -> a wider view (CHARCREATE_ZOOM.widths)

-- race icons: BfA's, sharp (RACE_ICON_ATLAS: RACE_SEX -> { left, right, top, bottom [, file] } in
-- RACE_ICON_ATLAS_FILE, filled at the end of this file); a race without one keeps its icon in
-- 3.3.5's own sheet (RACE_ICON_TCOORDS, which race packages add to)
RACE_ICON_FILE = "Interface\\Glues\\CharacterCreate\\UI-CharacterCreate-Races";
RACE_ICON_ATLAS = RACE_ICON_ATLAS or {};

FACTION_BACKDROP_COLOR_TABLE = {
	["Alliance"] = {0.5, 0.5, 0.5, 0.09, 0.09, 0.19, 0, 0, 0.2, 0.29, 0.33, 0.91},
	["Horde"] = {0.5, 0.2, 0.2, 0.19, 0.05, 0.05, 0.2, 0, 0, 0.90, 0.05, 0.07},
};
RACE_ICON_TCOORDS = {
	["HUMAN_MALE"]		= {0, 0.125, 0, 0.25},
	["DWARF_MALE"]		= {0.125, 0.25, 0, 0.25},
	["GNOME_MALE"]		= {0.25, 0.375, 0, 0.25},
	["NIGHTELF_MALE"]	= {0.375, 0.5, 0, 0.25},

	["TAUREN_MALE"]		= {0, 0.125, 0.25, 0.5},
	["SCOURGE_MALE"]	= {0.125, 0.25, 0.25, 0.5},
	["TROLL_MALE"]		= {0.25, 0.375, 0.25, 0.5},
	["ORC_MALE"]		= {0.375, 0.5, 0.25, 0.5},

	["HUMAN_FEMALE"]	= {0, 0.125, 0.5, 0.75},
	["DWARF_FEMALE"]	= {0.125, 0.25, 0.5, 0.75},
	["GNOME_FEMALE"]	= {0.25, 0.375, 0.5, 0.75},
	["NIGHTELF_FEMALE"]	= {0.375, 0.5, 0.5, 0.75},

	["TAUREN_FEMALE"]	= {0, 0.125, 0.75, 1.0},
	["SCOURGE_FEMALE"]	= {0.125, 0.25, 0.75, 1.0},
	["TROLL_FEMALE"]	= {0.25, 0.375, 0.75, 1.0},
	["ORC_FEMALE"]		= {0.375, 0.5, 0.75, 1.0},

	["BLOODELF_MALE"]	= {0.5, 0.625, 0.25, 0.5},
	["BLOODELF_FEMALE"]	= {0.5, 0.625, 0.75, 1.0},

	["DRAENEI_MALE"]	= {0.5, 0.625, 0, 0.25},
	["DRAENEI_FEMALE"]	= {0.5, 0.625, 0.5, 0.75},
};
CLASS_ICON_TCOORDS = {
	["WARRIOR"]	= {0, 0.25, 0, 0.25},
	["MAGE"]	= {0.25, 0.49609375, 0, 0.25},
	["ROGUE"]	= {0.49609375, 0.7421875, 0, 0.25},
	["DRUID"]	= {0.7421875, 0.98828125, 0, 0.25},
	["HUNTER"]	= {0, 0.25, 0.25, 0.5},
	["SHAMAN"]	= {0.25, 0.49609375, 0.25, 0.5},
	["PRIEST"]	= {0.49609375, 0.7421875, 0.25, 0.5},
	["WARLOCK"]	= {0.7421875, 0.98828125, 0.25, 0.5},
	["PALADIN"]	= {0, 0.25, 0.5, 0.75},
	["DEATHKNIGHT"]	= {0.25, 0.49609375, 0.5, 0.75},
};

-- the panels whose dark backgrounds take the faction's colour
local FACTION_PANELS = {
	"CharCreateRaceFramePanel", "CharCreateClassFrame", "CharCreateCustomizationFrame",
	"CharCreateRaceInfoFrame", "CharCreateClassInfoFrame",
};

function CharacterCreate_OnLoad(self)
	self:SetSequence(0);
	self:SetCamera(0);

	CharacterCreate.numRaces = 0;
	CharacterCreate.selectedRace = 0;
	CharacterCreate.numClasses = 0;
	CharacterCreate.selectedClass = 0;
	CharacterCreate.selectedGender = 0;
	CharacterCreate.races = {};
	CharacterCreate.alliedMode = nil;
	CharacterCreateFrame.state = "CLASSRACE";

	SetCharCustomizeFrame("CharacterCreate");

	for i=1, NUM_CHAR_CUSTOMIZATIONS, 1 do
		_G["CharacterCustomizationButtonFrame"..i.."Text"]:SetText(_G["CHAR_CUSTOMIZATION"..i.."_DESC"]);
	end

	CharCreateGenderLabel:SetText(CHAR_CUSTOMIZATION0_DESC);
	CharCreateAllianceLabel:SetText(ALLIANCE);
	CharCreateHordeLabel:SetText(HORDE);
	CharCreateClassLabel:SetText(CLASS);
	CharCreateCustomizationLabel:SetText(CUSTOMIZE_OPTIONS);
	CharacterCreateNameEditTitle:SetText(NAME);
	CharCreateAlliedRacesButton:SetText(CHARACTER_CREATE_MORE_RACES);
	CharCreateCoreRacesButton:SetText(CHARACTER_CREATE_CORE_RACES);
	CharCreateMoreInfoButton:SetText(CHAR_CREATE_MORE_INFO);

	-- the race box's panel and gender buttons draw over the banners hanging from it
	local level = CharCreateRaceFrame:GetFrameLevel();
	CharCreateRaceButtonsFrame:SetFrameLevel(level + 1);
	CharCreateRaceFramePanel:SetFrameLevel(level + 2);
	CharacterCreateGenderButtonMale:SetFrameLevel(level + 3);
	CharacterCreateGenderButtonFemale:SetFrameLevel(level + 3);

	-- Color edit box backdrop
	local backdropColor = FACTION_BACKDROP_COLOR_TABLE["Alliance"];
	CharacterCreateNameEdit:SetBackdropBorderColor(backdropColor[1], backdropColor[2], backdropColor[3]);
	CharacterCreateNameEdit:SetBackdropColor(backdropColor[4], backdropColor[5], backdropColor[6]);
end

function CharacterCreate_OnShow()
	for i=1, MAX_CLASSES_PER_RACE, 1 do
		local button = _G["CharacterCreateClassButton"..i];
		if ( button ) then
			button:Enable();
			SetButtonDesaturated(button, false)
		end
	end
	for i=1, MAX_RACES, 1 do
		local button = _G["CharacterCreateRaceButton"..i];
		if ( button ) then
			button:Enable();
			SetButtonDesaturated(button, false)
		end
	end

	if ( PAID_SERVICE_TYPE ) then
		CustomizeExistingCharacter( PAID_SERVICE_CHARACTER_ID );
		CharacterCreateNameEdit:SetText( PaidChange_GetName() );
	else
		--randomly selects a combination
		ResetCharCustomize();
		CharacterCreateNameEdit:SetText("");
		CharCreateRandomizeButton:Show();
	end

	CharacterCreate.currentScene = nil;
	CharacterCreate_SetState("CLASSRACE");

	CharacterCreateEnumerateRaces(GetAvailableRaces());
	SetCharacterRace(GetSelectedRace());

	CharacterCreateEnumerateClasses(GetAvailableClasses());
	local _,_,index = GetSelectedClass();
	SetCharacterClass(index);

	SetCharacterGender(GetSelectedSex())

	-- Hair customization stuff
	CharacterCreate_UpdateHairCustomization();

	SetCharacterCreateFacing(-15);

	-- setup customization
	CharacterChangeFixup();
end

function CharacterCreate_OnHide()
	PAID_SERVICE_CHARACTER_ID = nil;
	PAID_SERVICE_TYPE = nil;
	CharacterCreateTooltip:Hide();
	CharacterCreate_ResetZoom();
	CharacterCreate_SetShowcasePaused(false);
end

function CharacterCreateFrame_OnMouseDown(button)
	if ( button == "LeftButton" ) then
		CHARACTER_CREATE_ROTATION_START_X = GetCursorPosition();
		CHARACTER_CREATE_INITIAL_FACING = GetCharacterCreateFacing();
	end
end

function CharacterCreateFrame_OnMouseUp(button)
	if ( button == "LeftButton" ) then
		CHARACTER_CREATE_ROTATION_START_X = nil
	end
end

function CharacterCreateFrame_OnUpdate(self, elapsed)
	CharacterCreate_UpdateZoom(elapsed);
	CharacterCreate_PollCustomization(elapsed);
	if ( CHARACTER_CREATE_ROTATION_START_X ) then
		local x = GetCursorPosition();
		local diff = (x - CHARACTER_CREATE_ROTATION_START_X) * CHARACTER_ROTATION_CONSTANT;
		CHARACTER_CREATE_ROTATION_START_X = GetCursorPosition();
		SetCharacterCreateFacing(GetCharacterCreateFacing() + diff);
	end
end

-- --------------------------------------------------------------------------- the two steps

-- The forward button glows when it can go on, as BfA's (CharCreate_EnableNextButton): on the race
-- and class step always, on the customization step once the character has a name.
function CharacterCreate_UpdateOkayGlow()
	local ready = CharacterCreateFrame.state ~= "CUSTOMIZATION" or CharacterCreateNameEdit:GetText() ~= "";
	if ( ready ) then
		CharCreateOkayButtonTopGlow:Show();
		CharCreateOkayButtonBottomGlow:Show();
	else
		CharCreateOkayButtonTopGlow:Hide();
		CharCreateOkayButtonBottomGlow:Hide();
	end
end

-- "CLASSRACE": the gender box, race banners, class column and info panels; "CUSTOMIZATION": the
-- customization banner and the name (BfA's CharacterCreate_Forward / _Back).
function CharacterCreate_SetState(state)
	CharacterCreateFrame.state = state;
	if ( state == "CUSTOMIZATION" ) then
		CharCreateRaceFrame:Hide();
		CharCreateClassFrame:Hide();
		CharCreateRaceInfoFrame:Hide();
		CharCreateClassInfoFrame:Hide();
		CharCreateMoreInfoButton:Hide();
		CharCreateCustomizationFrame:Show();
		CharacterCreateNameEdit:Show();
		if ( ALLOW_RANDOM_NAME_BUTTON ) then
			CharacterCreateRandomName:Show();
		end
		CharCreateOkayButton:SetText(FINISH);
	else
		CharCreateRaceFrame:Show();
		CharCreateClassFrame:Show();
		CharCreateMoreInfoButton:Show();
		CharacterCreate_UpdateInfoPanels();
		CharCreateCustomizationFrame:Hide();
		CharacterCreateNameEdit:Hide();
		CharacterCreateRandomName:Hide();
		CharCreateOkayButton:SetText(CUSTOMIZE);
	end
	CharacterCreate_UpdateOkayGlow();
	CharacterCreate_UpdateRacesToggleButton();
	CharacterCreate_Zoom(state == "CUSTOMIZATION");
	CharacterCreate_SetShowcasePaused(state == "CUSTOMIZATION");
	if ( state == "CUSTOMIZATION" ) then
		CharacterCreate.customizationPage = 1;
		CharacterCreate_UpdateHairCustomization();
	end
end

-- The x64 client's class showcase (WarcraftXL creation effects) plays on the race and class step;
-- customizing, the character stands still.
function CharacterCreate_SetShowcasePaused(paused)
	if ( type(WXL_SetCreationEffectsCustomizationOpen) == "function" ) then
		WXL_SetCreationEffectsCustomizationOpen(paused and true or false);
	end
end

function CharacterCreate_Forward()
	if ( CharacterCreateFrame.state == "CLASSRACE" ) then
		PlaySound("gsCharacterSelectionCreateNew");
		CharacterCreate_SetState("CUSTOMIZATION");
		CharacterCreateNameEdit:SetFocus();
	else
		CharacterCreate_Okay();
	end
end

function CharacterCreate_Okay()
	if ( PAID_SERVICE_TYPE ) then
		GlueDialog_Show("CONFIRM_PAID_SERVICE");
	else
		CreateCharacter(CharacterCreateNameEdit:GetText());
	end
	PlaySound("gsCharacterCreationCreateChar");
end

function CharacterCreate_Back()
	if ( CharacterCreateFrame.state == "CUSTOMIZATION" ) then
		PlaySound("gsCharacterCreationCancel");
		CharacterCreate_SetState("CLASSRACE");
	else
		PlaySound("gsCharacterCreationCancel");
		SetGlueScreen("charselect");
	end
end

function CharacterCreate_ToggleMoreInfo()
	PlaySound("igMainMenuOptionCheckBoxOn");
	CharCreateMoreInfoButton.infoShown = not CharCreateMoreInfoButton.infoShown;
	CharacterCreate_UpdateInfoPanels();
end

function CharacterCreate_UpdateInfoPanels()
	local shown = CharCreateMoreInfoButton.infoShown and CharacterCreateFrame.state == "CLASSRACE";
	if ( shown ) then
		CharCreateRaceInfoFrame:Show();
		CharCreateClassInfoFrame:Show();
		CharCreateMoreInfoButtonTopGlow:Show();
		CharCreateMoreInfoButtonBottomGlow:Show();
		CharCreateMoreInfoButton:SetText(CHAR_CREATE_LESS_INFO);
	else
		CharCreateRaceInfoFrame:Hide();
		CharCreateClassInfoFrame:Hide();
		CharCreateMoreInfoButtonTopGlow:Hide();
		CharCreateMoreInfoButtonBottomGlow:Hide();
		CharCreateMoreInfoButton:SetText(CHAR_CREATE_MORE_INFO);
	end
end

-- --------------------------------------------------------------------------- races

local function CharCreate_RaceButton(index)
	local button = _G["CharacterCreateRaceButton"..index];
	if ( not button ) then
		button = CreateFrame("CheckButton", "CharacterCreateRaceButton"..index, CharCreateRaceButtonsFrame,
							 "CharCreateRaceButtonTemplate");
	end
	button:SetID(index);
	return button;
end

local function CharCreate_Gender()
	if ( GetSelectedSex() == SEX_FEMALE ) then
		return "FEMALE";
	end
	return "MALE";
end

local function CharCreate_SetRaceIcon(button, key, gender)
	local file, coords = nil, RACE_ICON_ATLAS[key.."_"..gender];
	if ( coords ) then
		file = coords[5] or RACE_ICON_ATLAS_FILE;
	end
	if ( not file ) then
		file = RACE_ICON_FILE;
		coords = RACE_ICON_TCOORDS[key.."_"..gender] or RACE_ICON_TCOORDS["HUMAN_"..gender];
	end
	for _, part in ipairs({ "NormalTexture", "PushedTexture" }) do
		local texture = _G[button:GetName()..part];
		texture:SetTexture(file);
		texture:SetTexCoord(coords[1], coords[2], coords[3], coords[4]);
	end
end

function CharacterCreateEnumerateRaces(...)
	CharacterCreate.numRaces = select("#", ...)/3;
	if ( CharacterCreate.numRaces > MAX_RACES ) then
		message("Too many races!  Update MAX_RACES");
		return;
	end
	local gender = CharCreate_Gender();
	CharacterCreate.races = {};
	CharacterCreate.hasAlliedRaces = nil;
	for index=1, CharacterCreate.numRaces, 1 do
		local name, fileString, available = select(index * 3 - 2, ...);
		local key = strupper(fileString);
		local _, faction = GetFactionForRace(index);
		local race = { name = name, fileString = key, faction = faction, allied = not CHARCREATE_CORE_RACES[key] };
		CharacterCreate.races[index] = race;
		if ( race.allied ) then
			CharacterCreate.hasAlliedRaces = true;
		end

		local button = CharCreate_RaceButton(index);
		CharCreate_SetRaceIcon(button, key, gender);
		_G[button:GetName().."NameFrameText"]:SetText(name);
		button.name = name;
		if ( available == 1 ) then
			button.enable = true;
			SetButtonDesaturated(button);
			button.tooltip = nil;
			_G[button:GetName().."DisableTexture"]:Hide();
		else
			button.enable = false;
			SetButtonDesaturated(button, 1);
			button.tooltip = _G[key.."_DISABLED"];
			_G[button:GetName().."DisableTexture"]:Show();
		end
	end
	for i=CharacterCreate.numRaces + 1, MAX_RACES, 1 do
		local button = _G["CharacterCreateRaceButton"..i];
		if ( button ) then
			button:Hide();
		end
	end
	CharacterCreate_LayoutRaces();
end

-- The races of the page shown (core or allied) down their faction's banner, the banners and the
-- page toggle to match.
function CharacterCreate_LayoutRaces()
	local rows = { Alliance = 0, Horde = 0 };
	for index=1, CharacterCreate.numRaces, 1 do
		local race = CharacterCreate.races[index];
		local button = _G["CharacterCreateRaceButton"..index];
		if ( (race.allied and 1 or 0) == (CharacterCreate.alliedMode and 1 or 0) ) then
			local column = "Alliance";
			local x = -CHARCREATE_RACE_COLUMN;
			if ( race.faction == "Horde" ) then
				column = "Horde";
				x = CHARCREATE_RACE_COLUMN;
			end
			button:ClearAllPoints();
			button:SetPoint("TOP", CharCreateRaceButtonsFrame, "TOP", x, CHARCREATE_RACE_TOP - rows[column] * CHARCREATE_RACE_ROW);
			rows[column] = rows[column] + 1;
			button:Show();
		else
			button:Hide();
		end
	end
	-- BfA's banners are drawn for six races a side (and its classic page hangs the Pandaren's under
	-- them): as long as the page's races need, drawn shorter rather than cut - a cut shows
	local count = math.max(rows.Alliance, rows.Horde, CHARCREATE_BANNER_MIN_ROWS);
	CharCreateRaceButtonsFrameBanners:SetHeight(CHARCREATE_BANNER_HEIGHT + (count - CHARCREATE_BANNER_ROWS) * CHARCREATE_RACE_ROW);
	CharacterCreate_UpdateRacesToggleButton();
end

function CharacterCreate_UpdateRacesToggleButton()
	if ( CharacterCreate.hasAlliedRaces and CharacterCreateFrame.state == "CLASSRACE" ) then
		if ( CharacterCreate.alliedMode ) then
			CharCreateAlliedRacesButton:Hide();
			CharCreateCoreRacesButton:Show();
		else
			CharCreateAlliedRacesButton:Show();
			CharCreateCoreRacesButton:Hide();
		end
	else
		CharCreateAlliedRacesButton:Hide();
		CharCreateCoreRacesButton:Hide();
	end
end

-- The first enabled race of a page, to select when the page changes.
local function CharCreate_FirstRaceOfPage(allied)
	local first;
	for index=1, CharacterCreate.numRaces, 1 do
		local race = CharacterCreate.races[index];
		if ( (race.allied and 1 or 0) == (allied and 1 or 0) ) then
			local button = _G["CharacterCreateRaceButton"..index];
			if ( button.enable and button:IsEnabled() ) then
				return index;
			end
			first = first or index;
		end
	end
	return first;
end

function CharacterCreate_ShowRacePage(allied)
	PlaySound("gsCharacterCreationClass");
	CharacterCreate.alliedMode = allied;
	CharacterCreate_LayoutRaces();
	local race = CharacterCreate.races[CharacterCreate.selectedRace];
	if ( not race or (race.allied and 1 or 0) ~= (allied and 1 or 0) ) then
		local index = CharCreate_FirstRaceOfPage(allied);
		if ( index ) then
			CharacterRace_OnClick(_G["CharacterCreateRaceButton"..index], index, true);
		end
	end
end

-- Racial text; a race on both sides (one ClientFileString) may have it per faction.
function CharacterCreate_AbilityText(fileString, faction)
	local key = "ABILITY_INFO_"..fileString;
	local factionKey = key.."_"..strupper(faction or "");
	if ( _G[factionKey.."1"] ) then
		key = factionKey;
	end
	local text, index = "", 1;
	while ( _G[key..index] ) do
		text = text.._G[key..index].."\n\n";
		index = index + 1;
	end
	return text;
end

function SetCharacterRace(id)
	CharacterCreate.selectedRace = id;
	for i=1, CharacterCreate.numRaces, 1 do
		local button = _G["CharacterCreateRaceButton"..i];
		if ( i == id ) then
			button:SetChecked(1);
		else
			button:SetChecked(nil);
		end
	end
	local race = CharacterCreate.races[id];
	if ( race and (race.allied and 1 or 0) ~= (CharacterCreate.alliedMode and 1 or 0) ) then
		CharacterCreate.alliedMode = race.allied;
		CharacterCreate_LayoutRaces();
	end

	-- Set Faction
	local _, faction = GetFactionForRace(CharacterCreate.selectedRace);

	-- Set Race
	local name, fileString = GetNameForRace();
	fileString = strupper(fileString);
	CharCreateRaceInfoFrameTitle:SetText(name);
	CharCreateRaceInfoFrameScrollFrameScrollBar:SetValue(0);
	CharCreateRaceInfoFrameScrollFrameScrollChildInfoText:SetText(GetFlavorText("RACE_INFO_"..fileString, GetSelectedSex()) or "");
	CharCreateRaceInfoFrameScrollFrameScrollChildBulletText:SetText(CharacterCreate_AbilityText(fileString, faction));
	CharacterCreate_ResizeInfo(CharCreateRaceInfoFrame);

	-- Set backdrop colors based on faction
	local backdropColor = FACTION_BACKDROP_COLOR_TABLE[faction] or FACTION_BACKDROP_COLOR_TABLE["Alliance"];
	for _, name in ipairs(FACTION_PANELS) do
		_G[name.."FactionBg"]:SetGradient("VERTICAL", 0, 0, 0, backdropColor[7], backdropColor[8], backdropColor[9]);
	end
	for _, part in ipairs({ "Top", "Middle", "Bottom" }) do
		_G["CharCreateCustomizationBanner"..part]:SetVertexColor(backdropColor[10], backdropColor[11], backdropColor[12]);
	end
	CharacterCreateNameEdit:SetBackdropColor(backdropColor[4], backdropColor[5], backdropColor[6]);

	-- the faction's scene (BfA creates every race of a faction in the same one)
	local scene = CHARCREATE_FACTION_SCENES[faction] or GetCreateBackgroundModel();
	if ( scene ~= CharacterCreate.currentScene ) then
		CharacterCreate.currentScene = scene;
		SetBackgroundModel(CharacterCreate, scene);
		-- a new scene starts on its own camera (SetLighting)
		CharacterCreate_ResetZoom();
		if ( CharacterCreateFrame.state == "CUSTOMIZATION" ) then
			CharacterCreate_Zoom(true);
		end
	end
end

function CharacterRace_OnClick(self, id, forceSelect)
	PlaySound("gsCharacterCreationClass");
	if ( not self:GetChecked() and not forceSelect ) then
		self:SetChecked(1);
		return;
	end
	if ( GetSelectedRace() ~= id ) then
		SetSelectedRace(id);
		SetCharacterRace(id);
		SetSelectedSex(GetSelectedSex());
		SetCharacterCreateFacing(-15);
		CharacterCreateEnumerateClasses(GetAvailableClasses());
		local _,_,classIndex = GetSelectedClass();
		if ( PAID_SERVICE_TYPE ) then
			classIndex = PaidChange_GetCurrentClassIndex();
		end
		SetCharacterClass(classIndex);

		-- Hair customization stuff
		CharacterCreate_UpdateHairCustomization();

		CharacterChangeFixup();
	else
		self:SetChecked(1);
	end
end

function CharCreateRaceButton_OnEnter(self)
	local race = CharacterCreate.races[self:GetID()];
	if ( not race ) then
		return;
	end
	local text = "|cffffd200"..race.name.."|r";
	local info = GetFlavorText("RACE_INFO_"..race.fileString, GetSelectedSex());
	if ( info and info ~= "" ) then
		text = text.."|n|n"..info;
	end
	if ( self.tooltip ) then
		text = text.."|n|n|cffff2020"..self.tooltip.."|r";
	end
	CharacterCreate_ShowTooltip(self, text, 260);
end

-- --------------------------------------------------------------------------- classes

local function CharCreate_ClassButton(index)
	local button = _G["CharacterCreateClassButton"..index];
	if ( not button ) then
		button = CreateFrame("CheckButton", "CharacterCreateClassButton"..index, CharCreateClassFrame,
							 "CharCreateClassButtonTemplate");
	end
	button:SetID(index);
	return button;
end

function CharacterCreateEnumerateClasses(...)
	CharacterCreate.numClasses = select("#", ...)/3;
	if ( CharacterCreate.numClasses > MAX_CLASSES_PER_RACE ) then
		message("Too many classes!  Update MAX_CLASSES_PER_RACE");
		return;
	end
	-- BfA's order: the Death Knight last (its layoutIndex 99), down from under the column's title
	local deathKnight;
	for index=1, CharacterCreate.numClasses, 1 do
		if ( strupper(select(index * 3 - 1, ...)) == "DEATHKNIGHT" ) then
			deathKnight = index;
		end
	end
	local top = CHARCREATE_CLASS_TOP;
	for index=1, CharacterCreate.numClasses, 1 do
		local name, fileString, available = select(index * 3 - 2, ...);
		local slot = index;
		if ( index == deathKnight ) then
			slot = CharacterCreate.numClasses;
		elseif ( deathKnight and index > deathKnight ) then
			slot = index - 1;
		end
		local coords = CLASS_ICON_TCOORDS[strupper(fileString)];
		local button = CharCreate_ClassButton(index);
		_G[button:GetName().."NormalTexture"]:SetTexCoord(coords[1], coords[2], coords[3], coords[4]);
		_G[button:GetName().."PushedTexture"]:SetTexCoord(coords[1], coords[2], coords[3], coords[4]);
		_G[button:GetName().."NameFrameText"]:SetText(name);
		button:ClearAllPoints();
		button:SetPoint("TOP", CharCreateClassLabel, "BOTTOM", 0, top - (slot - 1) * CHARCREATE_CLASS_ROW);
		button:Show();
		button.name = name;
		button.fileString = strupper(fileString);
		if ( (available == 1) and (IsRaceClassValid(CharacterCreate.selectedRace, index)) ) then
			button.enable = true;
			button:Enable();
			SetButtonDesaturated(button);
			button.tooltip = nil;
			_G[button:GetName().."DisableTexture"]:Hide();
		else
			button.enable = false;
			button:Disable();
			SetButtonDesaturated(button, 1);
			button.tooltip = _G[strupper(fileString).."_".."DISABLED"];
			_G[button:GetName().."DisableTexture"]:Show();
		end
	end
	for i=CharacterCreate.numClasses + 1, MAX_CLASSES_PER_RACE, 1 do
		local button = _G["CharacterCreateClassButton"..i];
		if ( button ) then
			button:Hide();
		end
	end
end

function SetCharacterClass(id)
	CharacterCreate.selectedClass = id;
	for i=1, CharacterCreate.numClasses, 1 do
		local button = _G["CharacterCreateClassButton"..i];
		if ( i == id ) then
			button:SetChecked(1);
		else
			button:SetChecked(nil);
		end
	end

	local className, classFileName = GetSelectedClass();
	local abilityIndex = 0;
	local tempText = _G["CLASS_INFO_"..classFileName..abilityIndex];
	local abilityText = "";
	while ( tempText ) do
		abilityText = abilityText..tempText.."\n\n";
		abilityIndex = abilityIndex + 1;
		tempText = _G["CLASS_INFO_"..classFileName..abilityIndex];
	end
	CharCreateClassInfoFrameTitle:SetText(className);
	CharCreateClassInfoFrameScrollFrameScrollBar:SetValue(0);
	CharCreateClassInfoFrameScrollFrameScrollChildInfoText:SetText(GetFlavorText("CLASS_"..strupper(classFileName), GetSelectedSex()) or "");
	CharCreateClassInfoFrameScrollFrameScrollChildBulletText:SetText(abilityText);
	CharacterCreate_ResizeInfo(CharCreateClassInfoFrame);
end

function CharacterClass_OnClick(id)
	PlaySound("gsCharacterCreationClass");
	local _,_,currClass = GetSelectedClass();
	if ( currClass ~= id and IsRaceClassValid(GetSelectedRace(), id) ) then
		SetSelectedClass(id);
		SetCharacterClass(id);
		SetCharacterRace(GetSelectedRace());
		CharacterChangeFixup();
	else
		SetCharacterClass(currClass);
	end
end

function CharCreateClassButton_OnEnter(self)
	local text = "|cffffd200"..(self.name or "").."|r";
	local roles = self.fileString and _G["CLASS_INFO_"..self.fileString.."0"];
	if ( roles ) then
		text = text.."|n"..roles;
	end
	if ( self.tooltip ) then
		text = text.."|n|n|cffff2020"..self.tooltip.."|r";
	end
	CharacterCreate_ShowTooltip(self, text, 220);
end

-- --------------------------------------------------------------------------- gender, customization

function SetCharacterGender(sex)
	SetSelectedSex(sex);
	if ( sex == SEX_MALE ) then
		CharacterCreateGenderButtonMale:SetChecked(1);
		CharacterCreateGenderButtonFemale:SetChecked(nil);
	elseif ( sex == SEX_FEMALE ) then
		CharacterCreateGenderButtonMale:SetChecked(nil);
		CharacterCreateGenderButtonFemale:SetChecked(1);
	end

	-- Update race images to reflect gender
	CharacterCreateEnumerateRaces(GetAvailableRaces());
	CharacterCreateEnumerateClasses(GetAvailableClasses());
	SetCharacterRace(GetSelectedRace());

	local _,_,classIndex = GetSelectedClass();
	if ( PAID_SERVICE_TYPE ) then
		classIndex = PaidChange_GetCurrentClassIndex();
	end
	SetCharacterClass(classIndex);

	CharacterCreate_UpdateHairCustomization();
	CharacterChangeFixup();
end

function CharacterCustomization_Left(id)
	PlaySound("gsCharacterCreationLook");
	if ( not CharacterCreate_CycleRetail(id, -1) ) then
		CycleCharCustomization(id, -1);
	end
end

function CharacterCustomization_Right(id)
	PlaySound("gsCharacterCreationLook");
	if ( not CharacterCreate_CycleRetail(id, 1) ) then
		CycleCharCustomization(id, 1);
	end
end

function CharacterCreate_Randomize()
	PlaySound("gsCharacterCreationLook");
	RandomizeCharCustomization();
	CharacterCreate_UpdateHairCustomization();
end

function CharacterCreate_UpdateHairCustomization()
	if ( CharacterCreate_UpdateCustomizationRows() ) then
		return;
	end
	for i=1, 2 do
		_G["CharacterCustomizationButtonFrame"..i.."Text"]:SetText(_G["CHAR_CUSTOMIZATION"..i.."_DESC"]);
	end
	CharacterCustomizationButtonFrame3Text:SetText(_G["HAIR_"..GetHairCustomization().."_STYLE"]);
	CharacterCustomizationButtonFrame4Text:SetText(_G["HAIR_"..GetHairCustomization().."_COLOR"]);
	CharacterCustomizationButtonFrame5Text:SetText(_G["FACIAL_HAIR_"..GetFacialHairCustomization()]);
end

-- --------------------------------------------------------------------------- retail options

-- The x64 client draws a race with its retail body and offers its retail options (WarcraftXL:
-- WXL_GetRetailOptions, _GetRetailChoices, _GetRetailSelection, WXL_SetRetailChoice): each option
-- with more than one choice gets a row, its name and where its choice stands among its choices,
-- CHARCREATE_CUSTOMIZATION_ROWS to a page. The 3.3.5 client, or a race still on its 3.3.5 body,
-- keeps the five classic rows.
local function CharCreate_RetailOptions()
	if ( type(WXL_GetRetailOptions) ~= "function" ) then
		return nil;
	end
	local all = WXL_GetRetailOptions();
	if ( type(all) ~= "table" or #all == 0 ) then
		return nil;
	end
	local selection = type(WXL_GetRetailSelection) == "function" and WXL_GetRetailSelection() or {};
	local options = {};
	for i, option in ipairs(all) do
		if ( (option.count or 0) > 1 ) then
			option.selected = selection[i];
			table.insert(options, option);
		end
	end
	if ( #options == 0 ) then
		return nil;
	end
	return options;
end

-- An option's choices and the place of its current one among them.
local function CharCreate_RetailChoice(option)
	local choices = type(WXL_GetRetailChoices) == "function" and WXL_GetRetailChoices(option.id) or nil;
	if ( type(choices) ~= "table" or #choices == 0 ) then
		return nil, 0;
	end
	for i, choice in ipairs(choices) do
		if ( choice.id == option.selected ) then
			return choices, i;
		end
	end
	return choices, 1;
end

-- Fills the rows from the retail options; false (rows as 3.3.5 has them) when there are none.
function CharacterCreate_UpdateCustomizationRows()
	local options = CharCreate_RetailOptions();
	CharacterCreate.retailOptions = options;
	CharacterCreate.retailContext = type(WXL_GetRetailChoiceContext) == "function" and WXL_GetRetailChoiceContext() or nil;
	local perPage = options and CHARCREATE_CUSTOMIZATION_ROWS or NUM_CHAR_CUSTOMIZATIONS;
	local pages = options and math.ceil(#options / perPage) or 1;
	local page = math.max(1, math.min(CharacterCreate.customizationPage or 1, pages));
	CharacterCreate.customizationPage = page;
	local last = 0;
	for i=1, CHARCREATE_CUSTOMIZATION_ROWS do
		local row = _G["CharacterCustomizationButtonFrame"..i];
		local option = options and options[(page - 1) * perPage + i];
		row.option = option;
		if ( option ) then
			local choices, at = CharCreate_RetailChoice(option);
			local name = option.name;
			if ( not name or name == "" ) then
				name = CUSTOMIZE;
			end
			_G["CharacterCustomizationButtonFrame"..i.."Text"]:SetText(name.."  "..at.."/"..(choices and #choices or option.count));
			row:Show();
			last = i;
		elseif ( not options and i <= NUM_CHAR_CUSTOMIZATIONS ) then
			row:Show();
			last = i;
		else
			row:Hide();
		end
	end
	CharCreateCustomizationBannerMiddle:SetHeight(CHARCREATE_CUSTOMIZATION_BANNER + (last - NUM_CHAR_CUSTOMIZATIONS) * CHARCREATE_CUSTOMIZATION_ROW_HEIGHT);
	CharCreateRandomizeButton:ClearAllPoints();
	CharCreateRandomizeButton:SetPoint("TOP", "CharacterCustomizationButtonFrame"..math.max(last, 1), "BOTTOM", 0, -16);
	if ( pages > 1 ) then
		CharCreateCustomizationPrevPage:Show();
		CharCreateCustomizationNextPage:Show();
	else
		CharCreateCustomizationPrevPage:Hide();
		CharCreateCustomizationNextPage:Hide();
	end
	return options ~= nil;
end

-- Steps a retail row's option to its next or previous choice; false on a classic row.
function CharacterCreate_CycleRetail(id, delta)
	local row = _G["CharacterCustomizationButtonFrame"..id];
	local option = row and row.option;
	if ( not option or type(WXL_SetRetailChoice) ~= "function" ) then
		return false;
	end
	local choices, at = CharCreate_RetailChoice(option);
	if ( choices ) then
		local nextAt = (at - 1 + delta) % #choices + 1;
		WXL_SetRetailChoice(option.id, choices[nextAt].id);
	end
	CharacterCreate_UpdateHairCustomization();
	return true;
end

function CharacterCreate_CustomizationPage(delta)
	PlaySound("gsCharacterCreationLook");
	CharacterCreate.customizationPage = (CharacterCreate.customizationPage or 1) + delta;
	local options = CharacterCreate.retailOptions;
	local pages = options and math.ceil(#options / CHARCREATE_CUSTOMIZATION_ROWS) or 1;
	if ( CharacterCreate.customizationPage > pages ) then
		CharacterCreate.customizationPage = 1;
	elseif ( CharacterCreate.customizationPage < 1 ) then
		CharacterCreate.customizationPage = pages;
	end
	CharacterCreate_UpdateHairCustomization();
end

-- The native character rebuilds on its own (a race, sex or class change, a randomize): the rows
-- follow it whenever its choices change.
function CharacterCreate_PollCustomization(elapsed)
	if ( type(WXL_GetRetailChoiceContext) ~= "function" or not CharCreateCustomizationFrame:IsShown() ) then
		return;
	end
	CharacterCreate.retailWait = (CharacterCreate.retailWait or 0) - (elapsed or 0);
	if ( CharacterCreate.retailWait > 0 ) then
		return;
	end
	CharacterCreate.retailWait = 0.2;
	if ( WXL_GetRetailChoiceContext() ~= CharacterCreate.retailContext ) then
		CharacterCreate_UpdateHairCustomization();
	end
	CharacterCreate_RetargetZoom();
end

-- --------------------------------------------------------------------------- the customize zoom

-- BfA glides to the character's head for customization. 3.3.5 has no camera call, so the scene
-- carries the glide (glue/zoom.py): a camera per head on a grid, which the scene's zoomIn
-- animation glides from the scene's view to that head and zoomOut back.
local function CharCreate_ZoomCamera()
	local zoom = CHARCREATE_ZOOM;
	if ( not zoom ) then
		return nil;
	end
	local _, fileString = GetNameForRace();
	local key = strupper(fileString or "").."_"..CharCreate_Gender();
	local head = CHARCREATE_ZOOM_HEAD[key];
	-- the x64 client measures the character it draws (a retail body is not the one the table was
	-- measured on): its head as it stands now
	if ( type(WXL_GetCreationHeadSpot) == "function" ) then
		local up, forward = WXL_GetCreationHeadSpot();
		if ( up ) then
			head = { up, math.max(0, forward or 0) };
		end
	end
	if ( not head ) then
		return nil;
	end
	local k = math.floor((head[1] - zoom.first) / zoom.step + 0.5);
	local j = math.floor((head[2] or 0) / zoom.forwardStep + 0.5);
	k = math.max(0, math.min(zoom.count - 1, k));
	j = math.max(0, math.min(zoom.forwards - 1, j));
	local w = math.max(0, math.min((zoom.widths or 1) - 1, CHARCREATE_ZOOM_WIDE[key] or 0));
	return zoom.camera + (w * zoom.forwards + j) * zoom.count + k;
end

-- Glide to the head (zoomIn) or back to the scene's view, from wherever the glide is: zoomAt is
-- how far it has come (0: the scene's view, 1: the head), zoomTo where it's going.
function CharacterCreate_Zoom(zoomIn, retarget)
	local zoom = CHARCREATE_ZOOM;
	if ( not zoom ) then
		return;
	end
	local at = CharacterCreate.zoomAt or 0;
	if ( zoomIn ) then
		local camera = CharCreate_ZoomCamera();
		if ( not camera ) then
			return;
		end
		if ( camera ~= CharacterCreate.zoomCamera and not retarget ) then
			at = 0;
		end
		CharacterCreate.zoomCamera = camera;
		CharacterCreate:SetCamera(camera);
		CharacterCreate:SetSequenceTime(zoom.zoomIn, at * zoom.glide * 1000);
		CharacterCreate.zoomTo = 1;
	elseif ( CharacterCreate.zoomCamera ) then
		CharacterCreate:SetSequenceTime(zoom.zoomOut, (1 - at) * zoom.glide * 1000);
		CharacterCreate.zoomTo = 0;
	end
	CharacterCreate.zoomAt = at;
end

-- The glide's progress; out at the scene's view, back on its own camera.
function CharacterCreate_UpdateZoom(elapsed)
	local zoom = CHARCREATE_ZOOM;
	local to = CharacterCreate.zoomTo;
	if ( not zoom or not to or not CharacterCreate.zoomCamera ) then
		return;
	end
	local at = CharacterCreate.zoomAt or 0;
	local step = (elapsed or 0) / zoom.glide;
	if ( to > at ) then
		at = math.min(to, at + step);
	elseif ( to < at ) then
		at = math.max(to, at - step);
	end
	CharacterCreate.zoomAt = at;
	if ( to == 0 and at == 0 ) then
		CharacterCreate:SetCamera(0);
		CharacterCreate:SetSequence(0);
		CharacterCreate_ResetZoom();
	end
end

-- Zoomed in, the head moved (the character settled into Stand, a new model loaded): the glide goes
-- on, to the camera of where the head is now.
function CharacterCreate_RetargetZoom()
	if ( CharacterCreate.zoomTo == 1 and CharacterCreate.zoomCamera and CharCreate_ZoomCamera() ~= CharacterCreate.zoomCamera ) then
		CharacterCreate_Zoom(true, true);
	end
end

function CharacterCreate_ResetZoom()
	CharacterCreate.zoomCamera = nil;
	CharacterCreate.zoomTo = nil;
	CharacterCreate.zoomAt = 0;
end

-- --------------------------------------------------------------------------- shared

function CharacterCreate_OnChar()
end

function CharacterCreate_OnKeyDown(key)
	if ( key == "ESCAPE" ) then
		CharacterCreate_Back();
	elseif ( key == "ENTER" ) then
		CharacterCreate_Forward();
	elseif ( key == "PRINTSCREEN" ) then
		Screenshot();
	end
end

function CharacterCreate_UpdateModel(self)
	UpdateCustomizationScene();
	self:AdvanceTime();
end

function CharacterCreateRotateRight_OnUpdate(self)
	if ( self:GetButtonState() == "PUSHED" ) then
		SetCharacterCreateFacing(GetCharacterCreateFacing() + CHARACTER_FACING_INCREMENT);
	end
end

function CharacterCreateRotateLeft_OnUpdate(self)
	if ( self:GetButtonState() == "PUSHED" ) then
		SetCharacterCreateFacing(GetCharacterCreateFacing() - CHARACTER_FACING_INCREMENT);
	end
end

-- A tooltip that wraps at ``width`` (3.3.5's glue tooltip sizes itself to one line of text).
function CharacterCreate_ShowTooltip(owner, text, width)
	GlueTooltip_SetOwner(owner, CharacterCreateTooltip, -3, -5);
	CharacterCreateTooltipTextLeft1:SetWidth(width or 0);
	GlueTooltip_SetText(text, CharacterCreateTooltip);
end

function CharacterCreate_HideTooltip()
	CharacterCreateTooltip:Hide();
	CharacterCreateTooltipTextLeft1:SetWidth(0);
end

-- An info panel's height from its text, between CHARCREATE_INFO_MIN and _MAX (scrolls past it).
function CharacterCreate_ResizeInfo(frame)
	local name = frame:GetName();
	local child = _G[name.."ScrollFrameScrollChild"];
	local height = _G[name.."ScrollFrameScrollChildInfoText"]:GetHeight() + _G[name.."ScrollFrameScrollChildBulletText"]:GetHeight() + 20;
	child:SetHeight(height);
	frame:SetHeight(math.min(CHARCREATE_INFO_MAX, math.max(CHARCREATE_INFO_MIN, height + 80)));
end

function SetButtonDesaturated(button, desaturated, r, g, b)
	if ( not button ) then
		return;
	end
	local icon = button:GetNormalTexture();
	if ( not icon ) then
		return;
	end
	local shaderSupported = icon:SetDesaturated(desaturated);

	if ( not desaturated ) then
		r = 1.0;
		g = 1.0;
		b = 1.0;
	elseif ( not r or not shaderSupported ) then
		r = 0.5;
		g = 0.5;
		b = 0.5;
	end

	icon:SetVertexColor(r, g, b);
end

function GetFlavorText(tagname, sex)
	local primary, secondary;
	if ( sex == SEX_MALE ) then
		primary = "";
		secondary = "_FEMALE";
	else
		primary = "_FEMALE";
		secondary = "";
	end
	local text = _G[tagname..primary];
	if ( (text == nil) or (text == "") ) then
		text = _G[tagname..secondary];
	end
	return text;
end

function CharacterCreate_DeathKnightSwap(self)
	local _, classFilename = GetSelectedClass();
	if ( classFilename == "DEATHKNIGHT" ) then
		if (self.currentModel ~= "DEATHKNIGHT") then
			self.currentModel = "DEATHKNIGHT";
			self:SetNormalTexture("Interface\\Glues\\Common\\Glue-Panel-Button-Up-Blue");
			self:SetPushedTexture("Interface\\Glues\\Common\\Glue-Panel-Button-Down-Blue");
			self:SetHighlightTexture("Interface\\Glues\\Common\\Glue-Panel-Button-Highlight-Blue");
		end
	else
		if (self.currentModel == "DEATHKNIGHT") then
			self.currentModel = nil;
			self:SetNormalTexture("Interface\\Glues\\Common\\Glue-Panel-Button-Up");
			self:SetPushedTexture("Interface\\Glues\\Common\\Glue-Panel-Button-Down");
			self:SetHighlightTexture("Interface\\Glues\\Common\\Glue-Panel-Button-Highlight");
		end
	end
end

function CharacterChangeFixup()
	if ( PAID_SERVICE_TYPE ) then
		for i=1, MAX_CLASSES_PER_RACE, 1 do
			local button = _G["CharacterCreateClassButton"..i];
			if ( button and CharacterCreate.selectedClass ~= i ) then
				button:Disable();
				SetButtonDesaturated(button, true)
			end
		end

		for i=1, CharacterCreate.numRaces, 1 do
			local allow = false;
			if ( PAID_SERVICE_TYPE == PAID_FACTION_CHANGE ) then
				local faction = GetFactionForRace(PaidChange_GetCurrentRaceIndex());
				if ( (i == PaidChange_GetCurrentRaceIndex()) or ((GetFactionForRace(i) ~= faction) and (IsRaceClassValid(i,CharacterCreate.selectedClass))) ) then
					allow = true;
				end
			elseif ( PAID_SERVICE_TYPE == PAID_RACE_CHANGE ) then
				local faction = GetFactionForRace(PaidChange_GetCurrentRaceIndex());
				if ( (i == PaidChange_GetCurrentRaceIndex()) or ((GetFactionForRace(i) == faction) and (IsRaceClassValid(i,CharacterCreate.selectedClass))) ) then
					allow = true
				end
			elseif ( PAID_SERVICE_TYPE == PAID_CHARACTER_CUSTOMIZATION ) then
				if ( i == CharacterCreate.selectedRace ) then
					allow = true
				end
			end
			if (not allow) then
				local button = _G["CharacterCreateRaceButton"..i];
				button:Disable();
				SetButtonDesaturated(button, true)
			end
		end
	end
end
