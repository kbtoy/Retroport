/*
 * mod-retroport-racials: the server half of the racials retroport ports from BfA.
 *
 * A race package (`retroport race`) gives a race BfA's own racials as 3.3.5 spells; most need
 * nothing more (auras 3.3.5 has). What BfA does in a server script, this does - bound to the
 * spells by the package's SQL (spell_script_names, spell_proc), so a spell without its race
 * package installed is never touched.
 *
 * Kul Tiran - Brush It Off (291628): "Increases Versatility by 1%. When you take damage, heal for
 * 2% of that amount over 4 sec." 3.3.5 has no Versatility: the spell's own auras give its damage
 * and healing done (+1% each); its damage-taken half (0.5% less) is the unit hook below. The heal
 * is the aura's third effect (BfA's periodic dummy, 2): each hit taken starts the heal spell
 * (291843, two ticks, its buff shown as BfA's is) with 2% of the damage, and what a running heal
 * has left rolls into it; a low-level hit's fraction of a point waits for the next hit.
 *
 * Pandaren - three passives 3.3.5 has no aura for, each a dummy aura whose amount is BfA's:
 * Bouncy (107076, -50): "You take half falling damage." The fall's damage is dealt while the
 *   server handles the landing packet: the movement check before it marks the player, the damage
 *   hook scales the self-damage dealt while marked, the move hook after it clears the mark (before
 *   the under-the-map kill, which stays whole). The combat log line, sent before the damage is
 *   dealt, still says the whole fall.
 * Inner Peace (107074, 100): "You earn twice as much rested experience." What the server adds to
 *   the rest bonus while the player rests in game (Player::Update) or was away (at login: the
 *   characters row still holds the bonus they logged out with) is added again, 100% of it.
 * Epicurean (107072, 100): "receive 100% more of the stats from Well Fed effects." A script on
 *   every Well Fed buff (the race's SQL binds it) raises its stat amounts while they're worked out,
 *   so a refreshed buff keeps the bonus.
 *
 * Mag'har Orc (from retail) - Ancestral Call (274738): "Invoke the spirits of your ancestors,
 * granting you one of their powers for 15 sec." Retail's server picks the buff (one of your two
 * highest secondary stats); 3.3.5 characters have no mastery or versatility to rank, so this casts
 * one of the four at random, as BfA's did. The buffs are level-scaled ratings in retail, worth about
 * the same percent at every level: their 3.3.5 spells hold that percent (crit and haste 5%, in their
 * MOD_RATING aura), and spell_retroport_rating_pct turns it into the rating that gives it at the
 * player's level. Ferocity of the Frostwolf (mastery) and Might of the Blackrock (versatility) are
 * damage and healing done, Might's damage-taken half below as Brush It Off's. Savage Blood, Open
 * Skies and Sympathetic Vigor need nothing here (3.3.5's own auras; the pet's health through
 * AzerothCore's spell_pet_auras).
 *
 * Earthen (races 33/34, from retail; `retroport race-identity`, the user's picks of 2026-11-03):
 * Wide-Eyed Wonder (448924, dummy aura 200): exploration experience up by its amount (x3).
 * Ingest Minerals (436341, dummy aura): always Well Fed, no food. The player keeps one of the
 *   package's own Well Fed buffs (233910-233916: permanent, kept through death, not cancelled) -
 *   Stamina until a gem says otherwise; Ingest Gem (233901, an item-target cast like Prospecting)
 *   eats a gem and puts on the buff of its color. Food (an item whose spell is food, or food and
 *   drink) can't be used; drink can. A level-up puts the buff on again, so it grows with the level.
 * Quiet Contemplation (461063): seated, health a % of the maximum a second - 3.3.5's aura heals a
 *   flat amount, made the % here; mana is 3.3.5's own % aura.
 * Azerite Surge, Titan-Wrought Frame and Hyper Productive are plain spells.
 */

#include <cmath>
#include "DatabaseEnv.h"
#include "DataMap.h"
#include "Item.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellAuraEffects.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "SpellScript.h"
#include "SpellScriptLoader.h"
#include "Unit.h"

enum RetroportRacialSpells
{
    SPELL_KT_BRUSH_IT_OFF      = 291628,
    SPELL_KT_BRUSH_IT_OFF_HEAL = 291843,
    SPELL_PA_EPICUREAN         = 107072,
    SPELL_PA_INNER_PEACE       = 107074,
    SPELL_PA_BOUNCY            = 107076,
    SPELL_MO_ANCESTRAL_CALL    = 274738,
    SPELL_MO_RICTUS            = 274739,                    // Rictus of the Laughing Skull: critical strike
    SPELL_MO_ZEAL              = 274740,                    // Zeal of the Burning Blade: haste
    SPELL_MO_FEROCITY          = 274741,                    // Ferocity of the Frostwolf: mastery
    SPELL_MO_MIGHT             = 274742,                    // Might of the Blackrock: versatility
    SPELL_EA_WIDE_EYED_WONDER  = 448924,
    SPELL_EA_INGEST_MINERALS   = 436341,
    SPELL_EA_INGEST_GEM        = 233901,                    // the package's own: eat a gem
    SPELL_EA_FED_CRIT          = 233910,                    // its Well Fed buffs, one a gem color
    SPELL_EA_FED_HASTE         = 233911,
    SPELL_EA_FED_STAMINA       = 233912,
    SPELL_EA_FED_VERSATILITY   = 233913,
    SPELL_EA_FED_HIT           = 233914,
    SPELL_EA_FED_ATTACK_POWER  = 233915,
    SPELL_EA_FED_SPELL_POWER   = 233916,
};

constexpr uint32 RETROPORT_EARTHEN_FED[] = { SPELL_EA_FED_CRIT, SPELL_EA_FED_HASTE, SPELL_EA_FED_STAMINA,
    SPELL_EA_FED_VERSATILITY, SPELL_EA_FED_HIT, SPELL_EA_FED_ATTACK_POWER, SPELL_EA_FED_SPELL_POWER };

// the racials whose 3.3.5 form is Versatility's: their first aura is its damage and healing done (N%),
// and the damage they take is N/2% less (BfA: 1% Versatility is 0.5% less damage taken)
constexpr uint32 RETROPORT_VERSATILITY_SPELLS[] = { SPELL_KT_BRUSH_IT_OFF, SPELL_MO_MIGHT, SPELL_EA_FED_VERSATILITY };

// the per-player state the hooks share (Object::CustomData: each player's own, updated on its map)
struct RetroportLanding : public DataMap::Base
{
    bool landing = false;                                   // its landing packet is being handled
};

struct RetroportRest : public DataMap::Base
{
    float last = 0.0f;                                      // the rest bonus the last update left
};

constexpr char const* RETROPORT_LANDING = "retroport_landing";
constexpr char const* RETROPORT_REST = "retroport_rest";

// 291628 - Brush It Off (Kul Tiran)
class spell_retroport_brush_it_off : public AuraScript
{
    PrepareAuraScript(spell_retroport_brush_it_off);

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_KT_BRUSH_IT_OFF_HEAL });
    }

    bool CheckProc(ProcEventInfo& eventInfo)
    {
        DamageInfo* damageInfo = eventInfo.GetDamageInfo();
        return damageInfo && damageInfo->GetDamage() > 0;
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction();
        Unit* target = GetTarget();
        SpellInfo const* heal = sSpellMgr->GetSpellInfo(SPELL_KT_BRUSH_IT_OFF_HEAL);
        if (!target || !heal)
            return;

        // 2% of a low-level hit is a fraction of a point: it adds up until there is a point a tick
        _owed += CalculatePct(float(eventInfo.GetDamageInfo()->GetDamage()), aurEff->GetAmount());
        // a heal still running rolls into the new one, as BfA's does
        int32 left = 0;
        if (AuraEffect const* running = target->GetAuraEffect(SPELL_KT_BRUSH_IT_OFF_HEAL, EFFECT_0, target->GetGUID()))
            left = running->GetAmount() * std::max<int32>(running->GetTotalTicks() - int32(running->GetTickNumber()), 0);

        int32 amplitude = std::max<int32>(1, heal->Effects[EFFECT_0].Amplitude);
        int32 ticks = std::max<int32>(1, heal->GetMaxDuration() / amplitude);
        int32 perTick = int32((_owed + float(left)) / float(ticks));
        if (perTick <= 0)
            return;                                         // the running heal goes on; this waits
        _owed += float(left - perTick * ticks);
        target->CastCustomSpell(target, SPELL_KT_BRUSH_IT_OFF_HEAL, &perTick, nullptr, nullptr, true, nullptr, aurEff);
    }

    float _owed = 0.0f;                                     // healing earned, not yet in a heal

    void Register() override
    {
        DoCheckProc += AuraCheckProcFn(spell_retroport_brush_it_off::CheckProc);
        OnEffectProc += AuraEffectProcFn(spell_retroport_brush_it_off::HandleProc, EFFECT_2, SPELL_AURA_PERIODIC_DUMMY);
    }
};

// Epicurean (Pandaren) on every Well Fed buff: the auras that are its stats
class spell_retroport_epicurean : public AuraScript
{
    PrepareAuraScript(spell_retroport_epicurean);

    static bool IsStat(AuraType type)
    {
        switch (type)
        {
            case SPELL_AURA_MOD_STAT:
            case SPELL_AURA_MOD_RATING:
            case SPELL_AURA_MOD_ATTACK_POWER:
            case SPELL_AURA_MOD_RANGED_ATTACK_POWER:
            case SPELL_AURA_MOD_DAMAGE_DONE:
            case SPELL_AURA_MOD_HEALING_DONE:
            case SPELL_AURA_MOD_POWER_REGEN:
            case SPELL_AURA_MOD_RESISTANCE:
                return true;
            default:
                return false;
        }
    }

    void CalcAmount(AuraEffect const* aurEff, int32& amount, bool& /*canBeRecalculated*/)
    {
        Unit* owner = GetUnitOwner();
        if (!owner || !IsStat(aurEff->GetAuraType()))
            return;
        if (AuraEffect const* epicurean = owner->GetAuraEffect(SPELL_PA_EPICUREAN, EFFECT_0))
            amount += CalculatePct(amount, epicurean->GetAmount());
    }

    void Register() override
    {
        DoEffectCalcAmount += AuraEffectCalcAmountFn(spell_retroport_epicurean::CalcAmount, EFFECT_ALL, SPELL_AURA_ANY);
    }
};

// 274738 - Ancestral Call (Mag'har Orc): one of the four clan buffs, at random
class spell_retroport_ancestral_call : public SpellScript
{
    PrepareSpellScript(spell_retroport_ancestral_call);

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MO_RICTUS, SPELL_MO_ZEAL, SPELL_MO_FEROCITY, SPELL_MO_MIGHT });
    }

    void HandleAfterCast()
    {
        static constexpr uint32 buffs[] = { SPELL_MO_RICTUS, SPELL_MO_ZEAL, SPELL_MO_FEROCITY, SPELL_MO_MIGHT };
        if (Unit* caster = GetCaster())
            caster->CastSpell(caster, buffs[urand(0, 3)], true);
    }

    void Register() override
    {
        AfterCast += SpellCastFn(spell_retroport_ancestral_call::HandleAfterCast);
    }
};

// a retail rating scaled by level (Rictus, Zeal): its 3.3.5 aura holds the percent it is worth,
// made the rating that gives it at the owner's level (the first rating of its mask: melee for crit
// and haste - a hybrid's spell haste, which takes more rating, gets a little less)
class spell_retroport_rating_pct : public AuraScript
{
    PrepareAuraScript(spell_retroport_rating_pct);

    void CalcAmount(AuraEffect const* aurEff, int32& amount, bool& /*canBeRecalculated*/)
    {
        Player* player = GetUnitOwner() ? GetUnitOwner()->ToPlayer() : nullptr;
        uint32 mask = uint32(aurEff->GetMiscValue());
        if (!player || !mask)
            return;
        for (uint32 cr = 0; cr < MAX_COMBAT_RATING; ++cr)
            if (mask & (1u << cr))
            {
                float pctPerRating = player->GetRatingMultiplier(CombatRating(cr));
                if (pctPerRating > 0.0f)
                    amount = std::max<int32>(1, int32(std::lround(float(amount) / pctPerRating)));
                return;
            }
    }

    void Register() override
    {
        DoEffectCalcAmount += AuraEffectCalcAmountFn(spell_retroport_rating_pct::CalcAmount, EFFECT_ALL, SPELL_AURA_MOD_RATING);
    }
};

// the Well Fed an Ingest Minerals player has on (0: none)
static uint32 RetroportEarthenFed(Player* player)
{
    for (uint32 fed : RETROPORT_EARTHEN_FED)
        if (player->HasAura(fed))
            return fed;
    return 0;
}

// that Well Fed on, and no other of them
static void RetroportEarthenSetFed(Player* player, uint32 fed)
{
    for (uint32 other : RETROPORT_EARTHEN_FED)
        if (other != fed)
            player->RemoveAurasDueToSpell(other);
    player->RemoveAurasDueToSpell(fed);
    player->CastSpell(player, fed, true);
}

// a gem's Well Fed by its color (ItemSubclassGem): red critical strike, blue damage and healing done
// (versatility's 3.3.5 form), yellow Stamina, purple hit, green haste, orange attack power, meta spell
// power; simple and prismatic Stamina
static uint32 RetroportEarthenFedForGem(uint32 subclass)
{
    switch (subclass)
    {
        case 0: return SPELL_EA_FED_CRIT;
        case 1: return SPELL_EA_FED_VERSATILITY;
        case 3: return SPELL_EA_FED_HIT;
        case 4: return SPELL_EA_FED_HASTE;
        case 5: return SPELL_EA_FED_ATTACK_POWER;
        case 6: return SPELL_EA_FED_SPELL_POWER;
        default: return SPELL_EA_FED_STAMINA;
    }
}

// 233901 - Ingest Gem (Earthen): eats the gem it targets, its color picks the Well Fed. The gem goes
// after the cast, when the spell no longer uses its target.
class spell_retroport_ingest_gem : public SpellScript
{
    PrepareSpellScript(spell_retroport_ingest_gem);

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_EA_FED_CRIT, SPELL_EA_FED_HASTE, SPELL_EA_FED_STAMINA, SPELL_EA_FED_VERSATILITY,
                                   SPELL_EA_FED_HIT, SPELL_EA_FED_ATTACK_POWER, SPELL_EA_FED_SPELL_POWER });
    }

    SpellCastResult CheckCast()
    {
        Unit* caster = GetCaster();
        Item* gem = GetExplTargetItem();
        if (!caster || !caster->IsPlayer() || !gem || gem->GetOwnerGUID() != caster->GetGUID()
            || gem->GetTemplate()->Class != ITEM_CLASS_GEM)
            return SPELL_FAILED_BAD_TARGETS;
        return SPELL_CAST_OK;
    }

    void HandleAfterCast()
    {
        Player* player = GetCaster() ? GetCaster()->ToPlayer() : nullptr;
        Item* gem = GetExplTargetItem();
        if (!player || !gem || gem->GetOwnerGUID() != player->GetGUID())
            return;
        uint32 fed = RetroportEarthenFedForGem(gem->GetTemplate()->SubClass);
        uint32 count = 1;
        player->DestroyItemCount(gem, count, true);
        RetroportEarthenSetFed(player, fed);
    }

    void Register() override
    {
        OnCheckCast += SpellCheckCastFn(spell_retroport_ingest_gem::CheckCast);
        AfterCast += SpellCastFn(spell_retroport_ingest_gem::HandleAfterCast);
    }
};

// 461063 - Quiet Contemplation (Earthen): the health a tick is its amount in % of the maximum
class spell_retroport_quiet_contemplation : public AuraScript
{
    PrepareAuraScript(spell_retroport_quiet_contemplation);

    void CalcAmount(AuraEffect const* /*aurEff*/, int32& amount, bool& /*canBeRecalculated*/)
    {
        if (Unit* owner = GetUnitOwner())
            amount = int32(owner->CountPctFromMaxHealth(amount));
    }

    void Register() override
    {
        DoEffectCalcAmount += AuraEffectCalcAmountFn(spell_retroport_quiet_contemplation::CalcAmount, EFFECT_0,
                                                     SPELL_AURA_OBS_MOD_HEALTH);
    }
};

// Versatility's damage-taken half for the racials that give it; Bouncy's falls
class retroport_racials_unit_script : public UnitScript
{
public:
    retroport_racials_unit_script() : UnitScript("retroport_racials_unit_script", true, { UNITHOOK_ON_DAMAGE }) { }

    void OnDamage(Unit* attacker, Unit* victim, uint32& damage) override
    {
        if (!victim || !damage)
            return;
        for (uint32 spell : RETROPORT_VERSATILITY_SPELLS)
            if (AuraEffect const* versatility = victim->GetAuraEffect(spell, EFFECT_0))
                damage -= uint32(CalculatePct(float(damage), float(versatility->GetAmount()) / 2.0f));
        // a fall is the only damage a player deals itself while its landing packet is handled
        if (attacker == victim && victim->IsPlayer())
        {
            RetroportLanding* landing = victim->CustomData.Get<RetroportLanding>(RETROPORT_LANDING);
            if (landing && landing->landing)
            {
                landing->landing = false;
                if (AuraEffect const* bouncy = victim->GetAuraEffect(SPELL_PA_BOUNCY, EFFECT_0))
                    damage = uint32(std::max(0.0f, float(damage) * (100.0f + float(bouncy->GetAmount())) / 100.0f));
            }
        }
    }
};

// Bouncy's landing mark; Inner Peace's rest
class retroport_racials_player_script : public PlayerScript
{
public:
    retroport_racials_player_script() : PlayerScript("retroport_racials_player_script",
        { PLAYERHOOK_ANTICHEAT_CHECK_MOVEMENT_INFO, PLAYERHOOK_ON_LOGIN, PLAYERHOOK_ON_UPDATE }) { }

    // every movement packet, before the server handles it (and the fall damage of a landing)
    bool AnticheatCheckMovementInfo(Player* player, MovementInfo const& movementInfo, Unit* /*mover*/, bool /*jump*/) override
    {
        if (movementInfo.fallTime && !movementInfo.HasMovementFlag(MOVEMENTFLAG_FALLING) && player->HasAura(SPELL_PA_BOUNCY))
            player->CustomData.GetDefault<RetroportLanding>(RETROPORT_LANDING)->landing = true;
        return true;
    }

    void OnPlayerLogin(Player* player) override
    {
        AuraEffect const* peace = player->GetAuraEffect(SPELL_PA_INNER_PEACE, EFFECT_0);
        if (!peace)
            return;
        // what the load added for the time away: the row still holds the bonus at logout
        if (QueryResult result = CharacterDatabase.Query("SELECT `rest_bonus` FROM `characters` WHERE `guid` = {}",
                player->GetGUID().GetCounter()))
        {
            float gained = player->GetRestBonus() - (*result)[0].Get<float>();
            if (gained > 0.0f)
                player->SetRestBonus(player->GetRestBonus() + gained * float(peace->GetAmount()) / 100.0f);
        }
        player->CustomData.GetDefault<RetroportRest>(RETROPORT_REST)->last = player->GetRestBonus();
    }

    // after Player::Update, which adds the rest earned in game (every 10 sec or more, resting)
    void OnPlayerUpdate(Player* player, uint32 /*diff*/) override
    {
        RetroportRest* rest = player->CustomData.Get<RetroportRest>(RETROPORT_REST);
        if (!rest)
            return;
        float now = player->GetRestBonus();
        if (now > rest->last && player->HasPlayerFlag(PLAYER_FLAGS_RESTING))
            if (AuraEffect const* peace = player->GetAuraEffect(SPELL_PA_INNER_PEACE, EFFECT_0))
            {
                player->SetRestBonus(now + (now - rest->last) * float(peace->GetAmount()) / 100.0f);
                now = player->GetRestBonus();
            }
        rest->last = now;
    }
};

// Earthen: Ingest Minerals' Well Fed and its no food; Wide-Eyed Wonder's exploration
class retroport_racials_earthen_script : public PlayerScript
{
public:
    retroport_racials_earthen_script() : PlayerScript("retroport_racials_earthen_script",
        { PLAYERHOOK_ON_LOGIN, PLAYERHOOK_ON_LEVEL_CHANGED, PLAYERHOOK_CAN_USE_ITEM, PLAYERHOOK_ON_GIVE_EXP }) { }

    // the Well Fed it logged out with (a saved aura), else Stamina's
    void OnPlayerLogin(Player* player) override
    {
        if (player->HasSpell(SPELL_EA_INGEST_MINERALS) && !RetroportEarthenFed(player))
            RetroportEarthenSetFed(player, SPELL_EA_FED_STAMINA);
    }

    // put on again at the new level: its stats grow with the level (the ratings are worked out for it)
    void OnPlayerLevelChanged(Player* player, uint8 /*oldLevel*/) override
    {
        if (!player->HasSpell(SPELL_EA_INGEST_MINERALS))
            return;
        uint32 fed = RetroportEarthenFed(player);
        RetroportEarthenSetFed(player, fed ? fed : SPELL_EA_FED_STAMINA);
    }

    // no food: an item whose spell eats (food, or food and drink); drink alone is fine
    bool OnPlayerCanUseItem(Player* player, ItemTemplate const* proto, InventoryResult& result) override
    {
        if (!proto || proto->Class != ITEM_CLASS_CONSUMABLE || !player->HasSpell(SPELL_EA_INGEST_MINERALS))
            return true;
        for (auto const& spell : proto->Spells)
            if (SpellInfo const* info = spell.SpellId > 0 ? sSpellMgr->GetSpellInfo(spell.SpellId) : nullptr)
            {
                SpellSpecificType kind = info->GetSpellSpecific();
                if (kind == SPELL_SPECIFIC_FOOD || kind == SPELL_SPECIFIC_FOOD_AND_DRINK)
                {
                    result = EQUIP_ERR_CANT_DO_RIGHT_NOW;
                    return false;
                }
            }
        return true;
    }

    void OnPlayerGiveXP(Player* player, uint32& amount, Unit* /*victim*/, uint8 xpSource) override
    {
        if (xpSource != XPSOURCE_EXPLORE)
            return;
        if (AuraEffect const* wonder = player->GetAuraEffect(SPELL_EA_WIDE_EYED_WONDER, EFFECT_0))
            amount += uint32(CalculatePct(float(amount), float(wonder->GetAmount())));
    }
};

// clears Bouncy's landing mark once the packet is handled
class retroport_racials_movement_script : public MovementHandlerScript
{
public:
    retroport_racials_movement_script() : MovementHandlerScript("retroport_racials_movement_script",
        { MOVEMENTHOOK_ON_PLAYER_MOVE }) { }

    void OnPlayerMove(Player* player, MovementInfo /*movementInfo*/, uint32 /*opcode*/) override
    {
        if (RetroportLanding* landing = player->CustomData.Get<RetroportLanding>(RETROPORT_LANDING))
            landing->landing = false;
    }
};

void AddRetroportRacialsScripts()
{
    RegisterSpellScript(spell_retroport_brush_it_off);
    RegisterSpellScript(spell_retroport_epicurean);
    RegisterSpellScript(spell_retroport_ancestral_call);
    RegisterSpellScript(spell_retroport_rating_pct);
    RegisterSpellScript(spell_retroport_ingest_gem);
    RegisterSpellScript(spell_retroport_quiet_contemplation);
    new retroport_racials_unit_script();
    new retroport_racials_player_script();
    new retroport_racials_earthen_script();
    new retroport_racials_movement_script();
}
