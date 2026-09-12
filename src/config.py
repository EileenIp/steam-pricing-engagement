"""All tunable parameters for the project live here — no magic numbers in the pipeline code."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"

# Raw payloads are written here untransformed, one file per request, and the cache
# is keyed so a re-run never re-fetches. The cache *is* the raw-data archive the
# spec asks for — there is no separate "save the raw JSON" step to forget.
STEAMSPY_ALL_DIR = RAW_DATA_DIR / "steamspy_all"
STEAMSPY_APP_DIR = RAW_DATA_DIR / "steamspy_app"
STORE_APP_DIR = RAW_DATA_DIR / "store_app"
RESUME_FILE = RAW_DATA_DIR / "resume.json"

# --- SteamSpy ---

STEAMSPY_URL = "https://steamspy.com/api.php"

# SteamSpy's published limits: 1 request/second for single-app calls, 60 seconds
# between `all` pages. These are documented, not guessed. The full pull is long
# enough that getting throttled mid-run costs more than respecting the wait.
STEAMSPY_APP_DELAY_SECONDS = 1.0
STEAMSPY_ALL_DELAY_SECONDS = 60.0

# Fixed by the API. Here so the page-count arithmetic isn't a magic number.
STEAMSPY_PAGE_SIZE = 1000

# Hard stop. The catalogue is tens of thousands of apps; if paging hasn't ended by
# 100 pages something is wrong with the termination check, and an unbounded loop
# at 60s/page would run for hours before anyone noticed.
MAX_ALL_PAGES = 100

# --- Steam storefront ---

STORE_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"

# Valve publishes no limit for this endpoint. The community-reported ceiling is
# roughly 200 requests per 5 minutes; 1.5s spacing sits inside that and leaves
# headroom for the retry budget below.
STORE_DELAY_SECONDS = 1.5

# cc=au because the spec's price bands are in AUD. The currency code is recorded
# in every cached payload, so a later re-band can verify it rather than trust it.
STORE_COUNTRY = "au"
STORE_LANGUAGE = "en"

REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2.0

# --- Phase 1: the comparison set (Checkpoint 1, decided by Eileen 2026-09-13) ---

MIN_RELEASE_YEAR = 2015

# Owner floor, applied to the interval midpoint. 20,000 is not an arbitrary round
# number: SteamSpy's bottom band is literally "0 .. 20,000", midpoint 10,000, so
# this floor drops exactly that band and nothing else — it is band-aligned rather
# than a cut through the middle of one. The bias it introduces, to be stated on
# the page in one sentence: survivorship. Games that flopped are excluded, so the
# sample tilts toward titles that found an audience.
MIN_OWNERS_MIDPOINT = 20_000

# Headline engagement metric (Checkpoint 1b): median playtime forever, in minutes
# as SteamSpy reports it. Median over mean because playtime is savagely skewed —
# a handful of 4,000-hour players drag any mean off the map.
HEADLINE_METRIC = "median_forever"

# Robustness check: peak concurrent users per owner. This one divides by the owner
# interval, so it is the metric that actually moves under the sensitivity bounds.
ROBUSTNESS_METRIC = "ccu_per_owner"

# Every owner-dependent result is evaluated at all three (Checkpoint 0).
OWNER_BOUNDS = ("lower", "midpoint", "upper")

# Price bands in AUD, upper bound exclusive; None means open-ended (spec Phase 2).
PRICE_BANDS_AUD = ((0, 10), (10, 30), (30, 60), (60, None))

# --- Phase 2: engagement metric, replacing SteamSpy's empty playtime fields ---
#
# Verified live 2026-09-13: SteamSpy serves median_forever, average_forever,
# median_2weeks and average_2weeks, and all four are zero for all 1,000 apps on
# the first `all` page and for both spot-checked apps. Playtime is therefore
# taken from Steam review payloads instead - author.playtime_forever, which is
# populated. Decided by Eileen 2026-09-13 after the fields were found empty.

STEAM_APPREVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"

# filter=recent sorts newest-first by creation date, so an identical re-run
# returns an identical corpus. filter=all sorts by helpfulness and re-orders as
# votes accrue, which would make the sample unreproducible.
REVIEW_FILTER = "recent"
REVIEW_LANGUAGE = "all"
REVIEW_TYPE = "all"
REVIEW_PURCHASE_TYPE = "all"
REVIEWS_PER_PAGE = 100  # documented maximum; larger values are silently clamped

# Reviewers sampled per game before taking the median. 200 is two pages: enough
# that the median is stable, small enough that a few hundred games is a pull
# measured in minutes rather than days.
TARGET_REVIEWS_PER_GAME = 200

# Stop paging a game that has fewer reviews than the target.
MAX_REVIEW_PAGES_PER_GAME = 5

REVIEW_DELAY_SECONDS = 1.5
REVIEW_CACHE_DIR = RAW_DATA_DIR / "reviews"

# A game with too few reviewers gets no playtime figure at all rather than a
# median of five people.
MIN_REVIEWERS_FOR_MEDIAN = 30

# --- Stratified sampling ---
#
# The cohort is thousands of games and a review pull per game is ~3 seconds, so
# the playtime metric runs on a sample. Strata are (pricing, primary genre)
# because genre confounding is the project's core analytical move - sampling at
# random would leave the smaller genre cells too thin to compare within.
RANDOM_SEED = 42
GAMES_PER_STRATUM = 25
MIN_GAMES_PER_STRATUM = 8  # cells thinner than this are reported, not analysed

# --- Genre stratification on SteamSpy tags (Eileen, 2026-09-13) -------------
#
# Steam's storefront genres are three broad buckets - ELDEN RING is "Action, RPG",
# Dota 2 is "Action, Strategy". Correcting for genre confounding on those would be
# a weak correction, because the confound the project is about lives at the level
# of MOBA vs Souls-like, not Action vs RPG. SteamSpy's user tags carry that
# resolution, so stratification runs on tags instead.
#
# Tags cannot be used raw. Two problems, both visible in Dota 2's tag list:
#
#   1. CIRCULARITY. Its highest-voted tag is "Free to Play" at 60,040 votes,
#      three times the next. Taking the top tag would put every F2P game in a
#      "Free to Play" cell and every paid game elsewhere - the strata would
#      encode the pricing model, and no cell would contain both, which is exactly
#      the comparison the project exists to make. Business-model tags are
#      therefore excluded by name, below.
#   2. DESCRIPTORS. "Difficult", "Dark Fantasy", "Third Person", "Multiplayer",
#      "Indie" are not genres. A blocklist of these would never end, so the
#      vocabulary is an explicit allowlist: a tag counts as a genre only if it is
#      listed here. That makes every cell assignment inspectable - it can be said
#      exactly why any game landed in any stratum.
#
# The allowlist is a judgement call, and an incomplete one until the catalogue
# lands. `python -m src.cohort coverage` reports how many games it fails to
# classify and which tags they would otherwise have fallen into, so the gaps are
# measured rather than assumed.

PRICING_MODEL_TAGS = frozenset({
    "Free to Play",
    "Early Access",
})

GENRE_TAGS = frozenset({
    # shooters
    "FPS", "Third-Person Shooter", "Hero Shooter", "Looter Shooter",
    "Extraction Shooter", "Battle Royale", "Arena Shooter", "Twin Stick Shooter",
    "Bullet Hell", "Shoot 'Em Up", "Tactical Shooter", "Hunting",
    # role-playing
    "RPG", "Action RPG", "JRPG", "CRPG", "Tactical RPG", "Party-Based RPG",
    "Souls-like", "Dungeon Crawler", "Roguelike", "Roguelite",
    "Roguelike Deckbuilder", "MMORPG", "Massively Multiplayer",
    # strategy
    "Strategy", "RTS", "Real Time Tactics", "Turn-Based Strategy",
    "Turn-Based Tactics", "Grand Strategy", "4X", "Wargame", "Tower Defense",
    "Auto Battler", "MOBA", "Card Battler", "Deckbuilding",
    # simulation and management
    "Simulation", "City Builder", "Colony Sim", "Management", "Farming Sim",
    "Life Sim", "Dating Sim", "Immersive Sim", "Space Sim", "Flight",
    "Automobile Sim", "Base Building", "Crafting", "Sandbox",
    # action and platforming
    "Platformer", "2D Platformer", "3D Platformer", "Precision Platformer",
    "Metroidvania", "Hack and Slash", "Beat 'em up", "Fighting", "Stealth",
    "Action-Adventure", "Action", "Adventure",
    # survival and horror
    "Survival", "Open World Survival Craft", "Survival Horror", "Horror",
    "Psychological Horror",
    # puzzle, narrative, casual
    "Puzzle", "Puzzle Platformer", "Hidden Object", "Match 3", "Point & Click",
    "Visual Novel", "Interactive Fiction", "Choose Your Own Adventure",
    "Walking Simulator", "Card Game", "Board Game", "Trivia", "Word Game",
    "Idler", "Clicker", "Party Game", "Rhythm", "Music", "Casual",
    # sports and racing
    "Sports", "Racing", "Football (Soccer)", "Basketball", "Golf", "Fishing",
})

# A game whose tags contain nothing in the vocabulary lands here. Kept in the
# cohort - it still has a pricing model and an engagement figure - but never used
# to support a within-genre claim.
UNCLASSIFIED_GENRE = "Unclassified"
