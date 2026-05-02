#!/usr/bin/env python3
"""
Font Awesome Pro 6.7.2 manifest generator for VLLM icon localization training.

Parses CSS and TTF files to build a deterministic, deduplicated manifest of every
visual icon/style combination across all 16 non-brand styles and 1 brand style.
"""

import re
import os
import struct
import math
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, 'assets', 'fontawesome-pro-6.7.2-web')
OUTPUT_DIR = os.path.join(BASE_DIR, 'src', 'generated')
CSS_DIR = os.path.join(ASSETS_DIR, 'css')
FONT_DIR = os.path.join(ASSETS_DIR, 'webfonts')

ICONS_PER_PAGE = 40

NON_BRAND_STYLES = [
    {"name": "solid",                "className": "fa-solid",                   "fontFile": "fa-solid-900.ttf"},
    {"name": "regular",              "className": "fa-regular",                 "fontFile": "fa-regular-400.ttf"},
    {"name": "light",                "className": "fa-light",                   "fontFile": "fa-light-300.ttf"},
    {"name": "thin",                 "className": "fa-thin",                    "fontFile": "fa-thin-100.ttf"},
    {"name": "duotone solid",        "className": "fa-duotone",                 "fontFile": "fa-duotone-900.ttf"},
    {"name": "duotone regular",      "className": "fa-duotone fa-regular",      "fontFile": "fa-duotone-regular-400.ttf"},
    {"name": "duotone light",        "className": "fa-duotone fa-light",        "fontFile": "fa-duotone-light-300.ttf"},
    {"name": "duotone thin",         "className": "fa-duotone fa-thin",         "fontFile": "fa-duotone-thin-100.ttf"},
    {"name": "sharp solid",          "className": "fa-sharp fa-solid",          "fontFile": "fa-sharp-solid-900.ttf"},
    {"name": "sharp regular",        "className": "fa-sharp fa-regular",        "fontFile": "fa-sharp-regular-400.ttf"},
    {"name": "sharp light",          "className": "fa-sharp fa-light",          "fontFile": "fa-sharp-light-300.ttf"},
    {"name": "sharp thin",           "className": "fa-sharp fa-thin",           "fontFile": "fa-sharp-thin-100.ttf"},
    {"name": "sharp duotone solid",  "className": "fa-sharp-duotone fa-solid",  "fontFile": "fa-sharp-duotone-solid-900.ttf"},
    {"name": "sharp duotone regular","className": "fa-sharp-duotone fa-regular","fontFile": "fa-sharp-duotone-regular-400.ttf"},
    {"name": "sharp duotone light",  "className": "fa-sharp-duotone fa-light",  "fontFile": "fa-sharp-duotone-light-300.ttf"},
    {"name": "sharp duotone thin",   "className": "fa-sharp-duotone fa-thin",   "fontFile": "fa-sharp-duotone-thin-100.ttf"},
]

BRAND_STYLE = {"name": "brands", "className": "fa-brands", "fontFile": "fa-brands-400.ttf"}

# ─── TTF cmap parsing ─────────────────────────────────────────────────────────

def read_cmap_codepoints(ttf_path):
    """Return the set of Unicode codepoints present in a TTF font's cmap table."""
    with open(ttf_path, 'rb') as f:
        data = f.read()

    # Offset table: find cmap table offset
    num_tables = struct.unpack('>H', data[4:6])[0]
    cmap_offset = None
    for i in range(num_tables):
        base = 12 + i * 16
        tag = data[base:base + 4].decode('ascii', errors='replace')
        if tag == 'cmap':
            cmap_offset = struct.unpack('>I', data[base + 8:base + 12])[0]
            break

    if cmap_offset is None:
        return set()

    num_subtables = struct.unpack('>H', data[cmap_offset + 2:cmap_offset + 4])[0]
    codepoints = set()

    for i in range(num_subtables):
        base = cmap_offset + 4 + i * 8
        subtable_offset = cmap_offset + struct.unpack('>I', data[base + 4:base + 8])[0]
        fmt = struct.unpack('>H', data[subtable_offset:subtable_offset + 2])[0]

        if fmt == 4:
            seg_count = struct.unpack('>H', data[subtable_offset + 6:subtable_offset + 8])[0] // 2
            end_base   = subtable_offset + 14
            start_base = end_base + seg_count * 2 + 2
            delta_base = start_base + seg_count * 2
            ro_base    = delta_base + seg_count * 2
            glyph_id_base = ro_base + seg_count * 2

            for j in range(seg_count):
                end_cp   = struct.unpack('>H', data[end_base   + j*2: end_base   + j*2+2])[0]
                start_cp = struct.unpack('>H', data[start_base + j*2: start_base + j*2+2])[0]
                delta    = struct.unpack('>h', data[delta_base + j*2: delta_base + j*2+2])[0]
                ro       = struct.unpack('>H', data[ro_base    + j*2: ro_base    + j*2+2])[0]
                if start_cp == 0xFFFF:
                    break
                for cp in range(start_cp, end_cp + 1):
                    if ro == 0:
                        glyph = (cp + delta) & 0xFFFF
                    else:
                        ro_idx = (ro // 2) + (cp - start_cp) - (seg_count - j)
                        pos = glyph_id_base + ro_idx * 2
                        if pos + 2 <= len(data):
                            glyph = struct.unpack('>H', data[pos:pos+2])[0]
                            if glyph != 0:
                                glyph = (glyph + delta) & 0xFFFF
                        else:
                            glyph = 0
                    if glyph != 0:
                        codepoints.add(cp)

        elif fmt == 12:
            num_groups = struct.unpack('>I', data[subtable_offset + 12:subtable_offset + 16])[0]
            for j in range(num_groups):
                b = subtable_offset + 16 + j * 12
                start_cp, end_cp, _ = struct.unpack('>III', data[b:b+12])
                for cp in range(start_cp, end_cp + 1):
                    codepoints.add(cp)

    return codepoints


# ─── CSS parsing ──────────────────────────────────────────────────────────────

def parse_icon_css(css_path, brands=False):
    """
    Parse a Font Awesome CSS file and return a dict mapping class_name → (primary_cp, secondary_cp).
    For brand icons (brands=True), there is no --fa--fa; secondary_cp equals primary_cp.
    """
    with open(css_path, 'r', encoding='utf-8') as f:
        content = f.read()

    icons = {}

    if brands:
        # Brand format: .fa-name { --fa: "\XXXX"; }
        pattern = re.compile(
            r'\.(fa-[a-z0-9][a-z0-9-]*)\s*\{\s*'
            r'--fa:\s*"\\([0-9a-fA-F]+)";\s*\}'
        )
        for m in pattern.finditer(content):
            cls, primary = m.group(1), m.group(2)
            primary_cp = int(primary, 16)
            icons[cls] = (primary_cp, primary_cp)
    else:
        # Non-brand format: .fa-name { --fa: "\XXXX"; --fa--fa: "\XXXX\XXXX"; }
        pattern = re.compile(
            r'\.(fa-[a-z0-9][a-z0-9-]*)\s*\{\s*'
            r'--fa:\s*"\\([0-9a-fA-F]+)";\s*'
            r'--fa--fa:\s*"\\([0-9a-fA-F]+)\\([0-9a-fA-F]+)";\s*\}'
        )
        for m in pattern.finditer(content):
            cls, primary, sec1, sec2 = m.group(1), m.group(2), m.group(3), m.group(4)
            primary_cp = int(primary, 16)
            secondary_cp = int(sec2, 16) if sec2 != primary else primary_cp
            icons[cls] = (primary_cp, secondary_cp)

    return icons


# ─── Metadata generation ──────────────────────────────────────────────────────

# Curated high-quality metadata for common icons
CURATED_METADATA = {
    "house":                  ("House",                "house-shaped icon with a peaked roof, two side walls, and a centered doorway", "navigates to the home page or main dashboard", "return to the main starting area of the application"),
    "house-chimney":          ("House with Chimney",   "house-shaped icon with a peaked roof and a vertical chimney stack", "navigates to the home page", "return to the application home screen"),
    "magnifying-glass":       ("Magnifying Glass",     "circular magnifying lens with a diagonal handle extending from the lower right", "opens a search field or find dialog", "look for an item, file, command, or piece of text"),
    "magnifying-glass-plus":  ("Zoom In",              "magnifying glass with a plus symbol inside the lens", "zooms in or increases the view scale", "see more detail in the current content"),
    "magnifying-glass-minus": ("Zoom Out",             "magnifying glass with a minus symbol inside the lens", "zooms out or decreases the view scale", "get a wider view of the current content"),
    "floppy-disk":            ("Floppy Disk",          "square floppy disk icon with a label area at the top and a small circular notch", "saves the current file or document", "preserve the user's current work before leaving"),
    "folder":                 ("Folder",               "rectangular folder with a curved top tab on the left side", "opens a folder or file directory", "browse or organize stored files"),
    "folder-open":            ("Open Folder",          "open folder icon showing the inside of the container with a lifted front flap", "opens or expands a selected folder", "view the contents of a folder"),
    "file":                   ("File",                 "rectangular page icon with a folded upper-right corner", "creates or opens a file", "work with a document or data file"),
    "file-lines":             ("File with Lines",      "document page icon with horizontal text lines drawn across the body", "opens or views a text document", "read or edit a text-based file"),
    "trash-can":              ("Trash Can",            "cylindrical trash bin icon with a horizontal lid and vertical slot lines on the body", "deletes the selected item or moves it to trash", "remove unwanted content from the current workspace"),
    "pen-to-square":          ("Edit",                 "square document with a diagonal pen writing in the lower right corner", "opens the item in edit mode", "make changes to the selected content"),
    "pen":                    ("Pen",                  "diagonal pen nib icon pointing to the lower left", "activates a drawing or writing tool", "add handwritten annotations or freehand input"),
    "pencil":                 ("Pencil",               "diagonal pencil icon with an eraser at the top and pointed tip at the bottom", "enables text editing or drawing mode", "manually enter or modify content"),
    "gear":                   ("Gear",                 "cog-shaped icon with evenly spaced teeth around a hollow circular center", "opens settings or configuration options", "change preferences or adjust application behavior"),
    "gears":                  ("Gears",                "two interlocking cog wheels of different sizes", "opens advanced settings or system configuration", "configure multiple interconnected system options"),
    "sliders":                ("Sliders",              "three horizontal adjustment sliders at different vertical positions", "opens a controls panel or filter options", "fine-tune parameters or adjust multiple settings"),
    "user":                   ("User",                 "simple silhouette of a single person with a round head and shoulders", "opens the user profile or account page", "view or manage the current user's account"),
    "user-plus":              ("Add User",             "person silhouette with a plus symbol on the right side", "adds a new user or invites someone", "create a new account or add a team member"),
    "user-minus":             ("Remove User",          "person silhouette with a minus symbol on the right side", "removes a user from a list or group", "revoke access or delete a user account"),
    "user-check":             ("Verified User",        "person silhouette with a checkmark on the right side", "confirms or approves a user account", "verify identity or mark a user as trusted"),
    "user-xmark":             ("Remove User",          "person silhouette with an X symbol on the right side", "removes or blocks a user", "deny access or deactivate a user account"),
    "users":                  ("Users",                "two overlapping person silhouettes side by side", "opens a team, group, or contact list", "manage members of a group or organization"),
    "envelope":               ("Envelope",             "rectangular envelope icon with a pointed flap sealed at the top", "composes a new email or opens the inbox", "send a message or check incoming mail"),
    "bell":                   ("Bell",                 "symmetrical bell icon with a small clapper at the bottom", "opens notification center or alerts panel", "check recent alerts or turn on reminders"),
    "bell-slash":             ("Bell Slash",           "bell icon with a diagonal slash line across it", "mutes notifications or disables alerts", "stop receiving notifications for this item"),
    "calendar-days":          ("Calendar",             "calendar grid icon showing day cells with a header bar at top", "opens a calendar or date picker", "view or schedule an event on a specific date"),
    "calendar":               ("Calendar",             "blank calendar page with a header and binding holes at top", "opens a calendar view or date selector", "manage scheduled events and appointments"),
    "clock":                  ("Clock",                "circular clock face with hour and minute hands", "shows a timestamp or opens a time picker", "see when something happened or set a time"),
    "hourglass":              ("Hourglass",            "narrow-waisted hourglass with sand flowing from top to bottom chamber", "indicates a loading state or time-limited action", "wait for a process to complete"),
    "camera":                 ("Camera",               "rectangular camera body with a circular lens and a small viewfinder bump on top", "takes a photo or opens the camera", "capture a picture or scan a visual code"),
    "image":                  ("Image",                "rectangular frame icon with a small mountain and sun landscape inside", "inserts or views an image", "add a photo or graphic to the content"),
    "images":                 ("Images",               "two overlapping rectangular image frames", "opens an image gallery or photo library", "browse a collection of images"),
    "chart-line":             ("Line Chart",           "rectangular chart area with an upward-trending zigzag line", "opens analytics or trend visualization", "track changes over time or monitor progress"),
    "chart-bar":              ("Bar Chart",            "three vertical bars of increasing height from left to right", "opens a bar chart or comparison view", "compare values across different categories"),
    "chart-pie":              ("Pie Chart",            "circular pie chart divided into slice segments", "opens a proportional breakdown or pie chart view", "see how a total is divided among categories"),
    "chart-column":           ("Column Chart",         "three upright bars on a baseline, tallest in the center", "displays column-based comparisons or metrics", "compare grouped values at a glance"),
    "table-cells":            ("Table",                "rectangular grid divided into rows and columns of cells", "opens a spreadsheet or data table view", "view or edit data in a structured grid format"),
    "download":               ("Download",             "downward-pointing arrow entering a horizontal baseline tray", "downloads the selected file to the device", "save content from the cloud or server locally"),
    "upload":                 ("Upload",               "upward-pointing arrow leaving a horizontal baseline tray", "uploads a file to the server or cloud", "share a local file with a remote service"),
    "print":                  ("Print",                "rectangular printer body with a paper sheet feeding out of the top", "sends the current document to a printer", "make a physical copy of the document"),
    "lock":                   ("Lock",                 "padlock icon with a rounded shackle arching above the body", "locks or secures the current item or session", "prevent unauthorized changes or access"),
    "lock-open":              ("Unlock",               "open padlock with the shackle swung to one side", "unlocks or grants access to a locked item", "remove a restriction so the item can be edited"),
    "key":                    ("Key",                  "traditional key silhouette with a circular bow and two teeth on the blade", "opens authentication or manages access keys", "log in or manage credentials and permissions"),
    "shield":                 ("Shield",               "heraldic shield outline with a flat top and pointed bottom", "opens security settings or protection options", "review or change security and privacy controls"),
    "shield-halved":          ("Shield Half",          "shield icon with the left half filled and the right half outlined", "shows partial protection status or security level", "check the current security coverage or level"),
    "circle-question":        ("Question Circle",      "circle containing a bold question mark", "opens help documentation or a tooltip", "get more information about an unfamiliar feature"),
    "circle-info":            ("Info Circle",          "circle containing a lowercase letter i", "shows additional information or details", "learn more about the selected item or feature"),
    "triangle-exclamation":   ("Warning Triangle",     "equilateral triangle with a bold exclamation mark inside", "shows a warning or alerts the user to a problem", "address an issue before proceeding"),
    "circle-exclamation":     ("Exclamation Circle",   "circle containing a bold exclamation mark", "shows a critical alert or required action", "resolve an error or confirm important notice"),
    "check":                  ("Checkmark",            "diagonal checkmark or tick mark", "confirms a selection or marks a task as done", "indicate that an item is complete or correct"),
    "circle-check":           ("Check Circle",         "circle with a checkmark inside", "confirms a successful action or completed state", "acknowledge a completed step or approved item"),
    "xmark":                  ("X Mark",               "diagonal cross made of two intersecting strokes", "closes a dialog or cancels an action", "dismiss a panel, clear a field, or abort a task"),
    "circle-xmark":           ("X Circle",             "circle containing a bold X mark", "removes an item or dismisses a notification", "cancel a selection or close a badge"),
    "plus":                   ("Plus",                 "symmetrical plus sign with four equal arms", "adds a new item, row, or element", "create something new in the current context"),
    "minus":                  ("Minus",                "short horizontal dash line", "removes an item or decreases a value", "reduce a count or delete a selected row"),
    "arrow-left":             ("Left Arrow",           "leftward-pointing chevron arrow", "navigates to the previous page or item", "go back to the prior step or screen"),
    "arrow-right":            ("Right Arrow",          "rightward-pointing chevron arrow", "navigates to the next page or item", "advance to the next step or screen"),
    "arrow-up":               ("Up Arrow",             "upward-pointing chevron arrow", "scrolls up or moves the item upward", "go to the top or move content higher in the list"),
    "arrow-down":             ("Down Arrow",           "downward-pointing chevron arrow", "scrolls down or moves the item downward", "go to the bottom or move content lower in the list"),
    "arrows-rotate":          ("Refresh",              "two curved arrows forming a circular rotation symbol", "refreshes or reloads the current content", "fetch the latest data or retry a failed request"),
    "rotate-left":            ("Rotate Left",          "single curved arrow arcing counter-clockwise", "undoes the last action or rotates content left", "step back to a previous state"),
    "rotate-right":           ("Rotate Right",         "single curved arrow arcing clockwise", "redoes an undone action or rotates content right", "reapply a previously undone change"),
    "play":                   ("Play",                 "solid rightward-pointing triangle", "plays a media file or starts a process", "begin playback or start an automated sequence"),
    "pause":                  ("Pause",                "two vertical parallel bars side by side", "pauses playback or a running process", "temporarily halt the current action without stopping"),
    "stop":                   ("Stop",                 "solid square shape", "stops playback or terminates a process", "fully end the current media or operation"),
    "forward":                ("Fast Forward",         "two rightward-pointing triangles side by side", "fast-forwards or skips ahead in media", "jump to a later point in the content"),
    "backward":               ("Rewind",               "two leftward-pointing triangles side by side", "rewinds or skips backward in media", "go back to an earlier point in the content"),
    "shuffle":                ("Shuffle",              "two crossing diagonal arrows forming a shuffle symbol", "randomizes playback order", "listen to content in a random sequence"),
    "repeat":                 ("Repeat",               "two arrows forming a rectangular loop", "enables looped or repeated playback", "play the same content over again"),
    "volume-high":            ("Volume High",          "speaker cone icon with multiple curved sound waves radiating outward", "increases volume or opens audio controls", "make the sound louder"),
    "volume-low":             ("Volume Low",           "small speaker cone with a single small sound wave", "decreases volume or shows a low audio level", "reduce the volume or set it to a quieter level"),
    "volume-xmark":           ("Mute",                 "speaker cone with an X symbol beside it", "mutes or unmutes audio", "silence all sound output"),
    "microphone":             ("Microphone",           "tall cylindrical microphone body with a rounded top and base stand", "activates voice input or recording", "speak to the application or record audio"),
    "microphone-slash":       ("Microphone Off",       "microphone icon with a diagonal slash through it", "mutes the microphone or disables voice input", "stop voice recording or mute a call"),
    "headphones":             ("Headphones",           "arched headband connecting two circular ear cups", "opens audio settings or switches to headphone output", "listen privately using headphones"),
    "star":                   ("Star",                 "five-pointed star shape", "marks an item as a favorite or top-rated", "save something important for easy access later"),
    "star-half":              ("Half Star",            "five-pointed star half-filled from the left", "shows a fractional rating or partial favorite", "indicate a half-point score in a rating system"),
    "heart":                  ("Heart",                "classic heart shape with two rounded lobes at the top", "likes or favorites the selected content", "express approval or save content you enjoy"),
    "heart-crack":            ("Broken Heart",         "heart shape split down the middle with a jagged crack", "indicates a removed favorite or broken connection", "show that something was unliked or a relationship ended"),
    "bookmark":               ("Bookmark",             "rectangular ribbon shape with a pointed V-notch at the bottom", "saves the item to a reading list or bookmark collection", "remember this page or item for later reference"),
    "thumbs-up":              ("Thumbs Up",            "upward-pointing hand thumb with fingers folded beneath", "gives a positive reaction or upvote", "express agreement or approval of the content"),
    "thumbs-down":            ("Thumbs Down",          "downward-pointing hand thumb with fingers folded above", "gives a negative reaction or downvote", "express disapproval or flag poor quality content"),
    "comment":                ("Comment",              "speech bubble rectangle with a pointed tail in the lower left corner", "opens a comment thread or adds a note", "leave feedback or start a discussion"),
    "comments":               ("Comments",             "two overlapping speech bubbles", "opens a discussion thread or conversation view", "view and participate in a group conversation"),
    "share":                  ("Share",                "three connected dots forming a branching share symbol", "opens sharing options for the content", "send this to another person or platform"),
    "reply":                  ("Reply",                "curved arrow pointing left toward a message", "replies to the selected message or thread", "respond to someone's message or comment"),
    "paper-plane":            ("Send",                 "stylized paper airplane pointing to the upper right", "sends a message or submits a form", "deliver the composed message to its recipient"),
    "inbox":                  ("Inbox",                "rectangular tray with a downward arrow inside", "opens the incoming messages or tasks inbox", "check for new items that need attention"),
    "cart-shopping":          ("Shopping Cart",        "cart basket with two wheels and a handle", "opens the shopping cart or purchase summary", "review selected items before checking out"),
    "bag-shopping":           ("Shopping Bag",         "handled paper shopping bag with a folded-over top", "opens the shopping bag or saved items", "see what you have added to your purchase"),
    "credit-card":            ("Credit Card",          "rectangular card with a magnetic stripe and embossed line details", "opens payment options or billing settings", "enter or manage payment information"),
    "receipt":                ("Receipt",              "long narrow receipt paper with horizontal line entries", "shows a purchase receipt or transaction log", "review what was charged in a recent order"),
    "dollar-sign":            ("Dollar Sign",          "vertical line crossed by a bold S curve", "opens financial settings or currency options", "manage money, pricing, or billing information"),
    "location-dot":           ("Location Pin",         "teardrop map pin with a small dot in the center", "shows a location on a map or opens navigation", "find or share a geographic position"),
    "map":                    ("Map",                  "flat unfolded map with fold lines creating a grid pattern", "opens a map or geographic view", "navigate to a destination or explore an area"),
    "map-pin":                ("Map Pin",              "simple vertical pin with a round top", "drops a pin on a map location", "mark a specific place for reference"),
    "route":                  ("Route",                "curved line with start and end markers showing a travel path", "shows directions or a navigation route", "get step-by-step directions to a destination"),
    "location-arrow":         ("Navigation Arrow",     "arrow pointing diagonally to the upper right inside or above a location symbol", "opens turn-by-turn navigation", "start navigating to the selected location"),
    "phone":                  ("Phone",                "classic handset receiver icon with a curved body", "initiates a phone call or opens call settings", "call the displayed number or contact"),
    "phone-slash":            ("Phone Off",            "phone handset with a diagonal slash through it", "ends a call or disables phone functionality", "hang up or disable calling features"),
    "wifi":                   ("Wi-Fi",                "stacked curved arcs growing wider from bottom to top, representing wireless signal", "opens network settings or shows connection status", "connect to or troubleshoot a wireless network"),
    "battery-full":           ("Battery Full",         "wide horizontal battery body with a nub terminal on the right, fully filled", "shows battery status or opens power settings", "check how much charge remains in the device"),
    "cloud":                  ("Cloud",                "fluffy rounded cloud outline with a flat bottom", "opens cloud storage or sync settings", "access remotely stored files or services"),
    "cloud-arrow-up":         ("Upload to Cloud",      "cloud icon with an upward arrow inside", "uploads data to cloud storage", "back up or sync content to the cloud"),
    "cloud-arrow-down":       ("Download from Cloud",  "cloud icon with a downward arrow inside", "downloads data from cloud storage", "retrieve a file stored in the cloud"),
    "sun":                    ("Sun",                  "circular sun disc with short radiating rays around the edge", "toggles light mode or adjusts brightness", "switch to a bright or daytime display theme"),
    "moon":                   ("Moon",                 "crescent moon shape facing right", "toggles dark mode or night settings", "switch to a low-brightness display for nighttime"),
    "bolt":                   ("Lightning Bolt",       "jagged diagonal lightning bolt shape", "triggers a quick action or shows a power indicator", "perform a fast action or enable a power feature"),
    "fire":                   ("Fire",                 "flame shape with a tapered top and curved base", "shows trending content or a hot item", "view the most popular or currently trending content"),
    "leaf":                   ("Leaf",                 "single leaf shape with a central vein line", "indicates eco-friendly or natural content", "explore sustainability or nature-related features"),
    "globe":                  ("Globe",                "spherical earth icon with latitude and longitude line grids", "opens language settings or a global view", "change region, language, or view worldwide content"),
    "link":                   ("Link",                 "two oval chain link shapes interlocked together", "copies a shareable link or creates a hyperlink", "share a direct URL or connect related content"),
    "paperclip":              ("Paperclip",            "looped paperclip shape curving over itself", "attaches a file to a message or document", "add a file as an attachment"),
    "scissors":               ("Scissors",             "two blades spreading from a central pivot with two finger rings", "cuts selected content for clipboard", "remove content and place it on the clipboard"),
    "copy":                   ("Copy",                 "two overlapping rectangular document pages", "copies the selected content to the clipboard", "duplicate content for use elsewhere"),
    "paste":                  ("Paste",                "clipboard with a document being placed onto it", "pastes clipboard content into the current location", "insert previously copied content"),
    "filter":                 ("Filter",               "downward-pointing funnel or triangle shape", "opens filter options for the current list or data", "narrow down results to only matching items"),
    "sort":                   ("Sort",                 "three horizontal lines decreasing in length from top to bottom", "opens sorting options for the list", "reorder items by a chosen criterion"),
    "bars":                   ("Menu",                 "three evenly spaced horizontal lines stacked vertically", "opens the main navigation menu", "access top-level navigation links and sections"),
    "ellipsis":               ("Ellipsis",             "three small dots in a horizontal row", "opens an overflow menu with more options", "see additional actions not shown in the main toolbar"),
    "wand-magic-sparkles":    ("Magic Wand",           "magic wand with sparkle stars around the tip", "applies automatic formatting, enhancement, or AI assistance", "let the system improve or transform the content automatically"),
    "code":                   ("Code",                 "angle brackets forming a less-than and greater-than pair", "opens a code editor or views source code", "write or inspect raw code for the current item"),
    "terminal":               ("Terminal",             "rectangle with a command prompt chevron and cursor", "opens a terminal or command-line interface", "run shell commands or scripts directly"),
    "bug":                    ("Bug",                  "six-legged insect body with antenna details", "opens a bug report or debugging view", "report or investigate a software defect"),
    "database":               ("Database",             "stacked horizontal cylinder discs representing a data store", "opens database management or data browser", "view or modify stored records and tables"),
    "server":                 ("Server",               "rectangular server unit with indicator lights and drive bays", "opens server settings or infrastructure status", "manage or monitor back-end infrastructure"),
    "desktop":                ("Desktop Computer",     "wide monitor screen on a short stand", "opens desktop or screen sharing settings", "interact with a desktop computer or screen"),
    "laptop":                 ("Laptop",               "open clamshell laptop with a screen and keyboard", "opens device settings or laptop configuration", "work on a portable computer or manage laptop features"),
    "mobile-screen":          ("Mobile Phone",         "tall rounded-corner smartphone with a home indicator bar", "opens mobile settings or previews mobile layout", "switch to or configure the mobile view"),
    "tablet-screen-button":   ("Tablet",               "tall rectangular tablet with a physical button on the side", "opens tablet settings or switches to tablet mode", "view or configure content in tablet layout"),
    "keyboard":               ("Keyboard",             "rectangular keyboard with rows of key caps", "opens keyboard shortcuts or input settings", "configure keyboard input or learn shortcut keys"),
    "computer-mouse":         ("Mouse",                "oval mouse body with a vertical scroll wheel groove", "opens mouse or pointer settings", "configure the cursor or input device behavior"),
    "gamepad":                ("Gamepad",              "controller with two analog sticks and four face buttons", "opens game settings or connects a game controller", "play a game or configure controller input"),
    "rocket":                 ("Rocket",               "streamlined rocket ship pointing upward with exhaust flames", "launches or deploys an application or feature", "start a new project or release a deployment"),
    "lightbulb":              ("Lightbulb",            "rounded light bulb with a threaded base and glowing filament", "shows a tip, suggestion, or idea", "get an idea or enable a smart suggestion feature"),
    "eye":                    ("Eye",                  "open eye with a circular iris and round pupil at the center", "shows or previews hidden content", "reveal a password field or see a preview"),
    "eye-slash":              ("Eye Slash",            "eye icon with a diagonal slash line across it", "hides or conceals the current content", "mask a password or hide sensitive information"),
    "rotate":                 ("Rotate",               "curved circular arrow forming a full rotation loop", "rotates the selected item or resets orientation", "change the angle or reset the rotation of content"),
    "expand":                 ("Expand",               "four outward-pointing corner arrows", "expands or enlarges the current view to full screen", "maximize the element to fill the available space"),
    "compress":               ("Compress",             "four inward-pointing corner arrows meeting in the center", "collapses or reduces the view from full screen", "minimize the full-screen view back to normal size"),
    "maximize":               ("Maximize",             "a square outline with an arrow pointing to the upper-right corner", "maximizes the panel or window to its largest size", "use the full available screen space"),
    "minimize":               ("Minimize",             "horizontal dash line at the bottom of a window-like frame", "minimizes the panel or collapses the element", "shrink the element out of view temporarily"),
    "crop":                   ("Crop",                 "two right-angle corner handles overlapping to define a crop boundary", "opens the crop tool for images", "trim the image to a specific region"),
    "crosshairs":             ("Crosshairs",           "circle with horizontal and vertical lines crossing at the center", "targets a specific position or calibration point", "select a precise location or fine-tune alignment"),
    "align-left":             ("Align Left",           "three horizontal lines of different lengths all flush with the left edge", "aligns the selected content to the left margin", "move text or elements to start from the left"),
    "align-center":           ("Align Center",         "three horizontal lines of different lengths centered horizontally", "centers the selected content horizontally", "align text or elements to the middle of the container"),
    "align-right":            ("Align Right",          "three horizontal lines of different lengths flush with the right edge", "aligns the selected content to the right margin", "push text or elements to end at the right side"),
    "align-justify":          ("Justify",              "four identical-length horizontal lines spanning the full width", "justifies the selected text to both margins", "spread text evenly across the full line width"),
    "bold":                   ("Bold",                 "thick bold capital letter B", "applies bold weight to selected text", "make the selected text heavier and more prominent"),
    "italic":                 ("Italic",               "slanted italic capital letter I", "applies italic style to selected text", "add emphasis by slanting the selected text"),
    "underline":              ("Underline",            "capital letter U with a horizontal underline beneath it", "underlines the selected text", "add a line below text to indicate importance or a link"),
    "strikethrough":          ("Strikethrough",        "capital letter S with a horizontal line crossing through the middle", "applies a strikethrough to selected text", "mark text as removed or no longer relevant"),
    "list":                   ("List",                 "three horizontal lines each preceded by a small dot bullet", "switches to a list view or inserts a bullet list", "organize content into an unordered list"),
    "list-ol":                ("Numbered List",        "number 1 and short horizontal lines representing ordered list items", "inserts a numbered list or switches to ordered view", "organize items in a specific numbered sequence"),
    "grip":                   ("Grip",                 "a grid of evenly spaced small dots or circles", "activates drag-and-drop reordering mode", "rearrange items by dragging them to a new position"),
    "font":                   ("Font",                 "capital letter A with serif decorations or a baseline foot", "opens font selection settings", "change the typeface used for the selected text"),
    "heading":                ("Heading",              "capital letter H with a horizontal crossbar", "applies a heading style to selected text", "mark a line of text as a section title or heading"),
    "quote-left":             ("Quote",                "two small open double-quotation marks at the left", "inserts a block quote or citation", "add a quoted passage from an external source"),
    "language":               ("Language",             "globe or speech bubble with letter characters", "opens language or locale selection settings", "switch the application language or region"),
    "spell-check":            ("Spell Check",          "letters A and B with a checkmark and wavy underline detail", "runs spell check on the document", "find and correct spelling mistakes"),
    "tag":                    ("Tag",                  "rounded rectangular label with a small hole at the left and a pointed right end", "adds a tag or label to the item", "categorize content with a keyword or label"),
    "tags":                   ("Tags",                 "two tag shapes layered together", "manages multiple tags or opens a tag browser", "add or browse multiple categories and labels"),
    "flag":                   ("Flag",                 "rectangular flag shape attached to a vertical pole on the left", "flags, marks, or reports an item", "mark content for review or report an issue"),
    "award":                  ("Award",                "ribbon badge with a star at the top and decorative tails at the bottom", "shows an award or achievement level", "celebrate an earned recognition or rank"),
    "trophy":                 ("Trophy",               "two-handled cup on a short pedestal base", "shows a leaderboard or top achievement", "compete for the highest score or ranking"),
    "medal":                  ("Medal",                "circular medal disc hanging from a ribbon loop", "shows a medal or earned achievement", "recognize completion of a challenge or goal"),
    "gift":                   ("Gift",                 "wrapped box with a decorative ribbon and bow on top", "indicates a gift, reward, or promotional offer", "claim a bonus or view available rewards"),
    "palette":                ("Palette",              "rounded artist's palette with multi-color paint spots and a thumb hole", "opens color picker or theme settings", "choose a color or change the visual theme"),
    "brush":                  ("Paintbrush",           "long-handled brush with bristles at the tip and a tapered ferrule", "activates the brush drawing tool", "paint or draw on a canvas with the brush"),
    "droplet":                ("Water Drop",           "teardrop-shaped water droplet with a rounded bottom and tapered top", "opens fill or color tools", "apply a color fill or adjust liquid-related settings"),
    "eraser":                 ("Eraser",               "rectangular eraser block at an angle", "activates the eraser tool to remove drawn content", "rub out mistakes or clear drawn marks"),
    "ruler":                  ("Ruler",                "diagonal measuring ruler with evenly spaced tick marks", "toggles guide rulers or measurement tools", "measure distances or align elements precisely"),
    "compass-drafting":       ("Drafting Compass",     "drafting compass with a pivot joint and two arms spread apart", "opens precision drawing or geometry tools", "draw circles or arcs with exact measurements"),
    "hammer":                 ("Hammer",               "short-handled claw hammer with a rectangular metal head", "builds, constructs, or runs a build operation", "trigger a compilation or construction process"),
    "wrench":                 ("Wrench",               "open-ended wrench tool with an adjustable jaw", "opens repair tools or system maintenance options", "fix or adjust a component or setting"),
    "screwdriver-wrench":     ("Tools",                "crossed screwdriver and wrench forming an X shape", "opens developer tools or maintenance settings", "access utilities for fixing or configuring the system"),
    "plug":                   ("Plug",                 "electrical plug head with two rectangular prongs", "connects a service or activates an integration", "hook up a plugin or establish a connection"),
    "power-off":              ("Power",                "circle with a short vertical line at the top center", "powers off or shuts down the device or session", "turn off the device or log out of the session"),
    "calculator":             ("Calculator",           "rectangular calculator with a small display and grid of number buttons", "opens a calculator or numeric input tool", "perform arithmetic or compute a value"),
    "percent":                ("Percent",              "two small circles connected by a diagonal slash line", "opens percentage formatting or discount settings", "express a value as a fraction of one hundred"),
    "sitemap":                ("Sitemap",              "tree diagram of connected rectangular nodes", "opens an organizational chart or site structure view", "navigate the hierarchical structure of the application"),
    "diagram-project":        ("Project Diagram",      "connected nodes forming a project dependency or flow diagram", "shows project tasks or dependency relationships", "understand how steps in a project connect to each other"),
    "timeline":               ("Timeline",             "horizontal line with several vertical event markers at intervals", "opens a chronological view or event history", "review the sequence of past or planned events"),
    "truck":                  ("Truck",                "delivery truck with a rectangular cargo box on the back and cab at front", "tracks a shipment or opens delivery options", "check where a package is or schedule a delivery"),
    "car":                    ("Car",                  "sedan-style car silhouette with four wheels", "opens vehicle or transportation settings", "manage a car-related feature or request a ride"),
    "plane":                  ("Airplane",             "top-down view of a commercial airplane with swept wings and tail fins", "opens flight or travel information", "book a flight or check travel status"),
    "ship":                   ("Ship",                 "ocean ship with a hull, deck, and a smokestack or mast", "opens maritime or shipping information", "track a sea shipment or manage water transport"),
    "train":                  ("Train",                "front-view of a train engine with headlights and wheels", "opens transit or train schedule information", "view train routes or commute schedules"),
    "bicycle":                ("Bicycle",              "two-wheeled bicycle with pedals, handlebars, and a frame", "opens cycling routes or fitness tracking", "log a bike ride or find cycling directions"),
    "person-walking":         ("Person Walking",       "stick figure in mid-stride walking pose", "opens pedestrian directions or step tracking", "navigate on foot or view walking activity data"),
    "wheelchair":             ("Wheelchair",           "seated person in a wheelchair with large rear wheels", "opens accessibility settings or options", "configure accessibility features or accessible routes"),
    "hospital":               ("Hospital",             "building silhouette with a cross symbol on the facade", "shows a nearby hospital or medical facility", "find emergency care or medical services"),
    "stethoscope":            ("Stethoscope",          "circular chest piece connected to a curved tube ending in two earpieces", "opens health or medical records", "review health data or contact a medical professional"),
    "pills":                  ("Pills",                "two oval capsule pill shapes stacked or overlapping", "opens medication reminders or pharmacy information", "check prescriptions or set a medication schedule"),
    "heart-pulse":            ("Heartbeat",            "heart shape with an ECG pulse line running across the center", "opens vital signs or health monitoring data", "check your heart rate or health metrics"),
    "flask":                  ("Flask",                "round-bottomed chemistry flask with a narrow neck", "opens lab results, experiments, or beta features", "view experimental settings or testing data"),
    "microscope":             ("Microscope",           "optical microscope with an eyepiece, arm, and stage platform", "opens scientific analysis or detailed inspection", "examine data at a fine-grained detail level"),
    "atom":                   ("Atom",                 "nucleus with three elliptical electron orbits surrounding it", "opens scientific settings or physics-related content", "explore fundamental principles or atomic-level data"),
    "dna":                    ("DNA",                  "double helix spiral with connecting rungs between two twisted strands", "opens genetic or biometric information", "view biological data or genomic analysis"),
    "book":                   ("Book",                 "closed hardcover book with a visible spine binding", "opens documentation or a reading resource", "read reference material or learn about a topic"),
    "book-open":              ("Open Book",            "open book with two visible pages and a central binding spine", "opens reading mode or displays documentation", "read a guide, tutorial, or reference document"),
    "graduation-cap":         ("Graduation Cap",       "flat mortarboard cap with a hanging tassel", "opens educational content or a learning section", "access courses, tutorials, or academic resources"),
    "newspaper":              ("Newspaper",            "folded newspaper with horizontal headline text and column lines", "opens news feed or publication content", "read the latest articles or updates"),
    "clipboard":              ("Clipboard",            "rectangular clipboard with a spring clip at the top", "opens a task list or clipboard contents", "view copied items or manage pending tasks"),
    "clipboard-check":        ("Clipboard Check",      "clipboard with a checkmark drawn on the paper surface", "marks all tasks as complete or reviews a checklist", "confirm that all required steps have been completed"),
    "list-check":             ("Checklist",            "list of items each preceded by a small checkmark", "opens a to-do list or checklist view", "review and tick off items from a task list"),
    "square-check":           ("Checkbox Checked",     "square outline with a checkmark inside", "toggles a checkbox to the checked state", "select or confirm a specific option"),
    "up-right-from-square":   ("External Link",        "square outline with an arrow pointing to the upper right out of the corner", "opens the link in a new tab or external window", "view the content in a separate browser window"),
    "ban":                    ("Ban",                  "circle with a diagonal slash running from upper left to lower right", "blocks, disables, or forbids the selected item", "prevent an action or revoke permission"),
    "info":                   ("Info",                 "lowercase letter i centered on a small baseline", "shows contextual help or additional details", "get more information about the adjacent element"),
    "exclamation":            ("Exclamation",          "bold vertical exclamation mark with a dot at the base", "highlights something that requires attention", "draw attention to an important notice or alert"),
    "question":               ("Question Mark",        "bold question mark with a dot at the base", "shows a help tooltip or opens FAQ", "get an answer to a question or access help content"),
    "rss":                    ("RSS Feed",             "small square with three curved signal arcs radiating from the lower left corner", "subscribes to an RSS or content feed", "follow updates from a website or blog"),
    "podcast":                ("Podcast",              "microphone icon with curved signal wave arcs on either side", "opens a podcast player or subscription list", "listen to audio podcast episodes"),
    "music":                  ("Music Note",           "a single eighth note or pair of connected eighth notes", "opens the music player or audio library", "play music or access audio content"),
    "film":                   ("Film Strip",           "horizontal film strip with square perforation holes on both edges", "opens a video file or film library", "browse or play video content"),
    "video":                  ("Video Camera",         "rectangular video camera body with a triangular lens housing on the right", "starts video recording or opens video settings", "record a video or start a video call"),
    "video-slash":            ("Video Off",            "video camera with a diagonal slash through it", "disables the camera or turns off video", "stop sharing your camera in a call"),
    "compass":                ("Compass",              "circular compass rose with N/S/E/W directional points and a needle", "opens navigation or orientation tools", "find your direction or navigate to a new location"),
    "map-location-dot":       ("Map with Pin",         "folded map with a location pin dropped on it", "opens an interactive map view with a pinned location", "find or share a specific location on a map"),
}

# Category-based fallback metadata templates
# Each category: (appearance_template, functionality_template, intent_template)
CATEGORY_TEMPLATES = {
    "circle_variant": (
        "circular icon containing a {inner} symbol",
        "indicates a {inner}-related status or action",
        "interact with or get information about a {inner} state"
    ),
    "face_emoji": (
        "circular face icon with a {expression} facial expression",
        "inserts a {expression} emoji or reaction",
        "express a {expression} sentiment in conversation"
    ),
    "person_figure": (
        "person silhouette icon showing {detail}",
        "opens a user or person-related feature with {detail}",
        "manage or interact with a person's information or status"
    ),
    "arrow_direction": (
        "arrow pointing {direction} with a clean angular tip",
        "moves or navigates content {direction}",
        "go {direction} or shift the selected item in that direction"
    ),
    "building_structure": (
        "building icon with {detail} architectural features",
        "opens location information for a {type} building",
        "find or navigate to a {type} location"
    ),
    "shape_symbol": (
        "geometric {shape} shape",
        "represents a visual marker or selection state",
        "mark, select, or organize content using this shape"
    ),
    "number_letter": (
        "typographic {char} character or numeral",
        "represents or inserts the {char} character",
        "use the {char} symbol in text or as a numbered identifier"
    ),
    "file_document": (
        "document or file page icon with {detail}",
        "opens, creates, or manages a {type} file",
        "work with a {type} document or data file"
    ),
    "media_control": (
        "media control icon showing {symbol}",
        "controls media playback by {action}",
        "interact with audio or video at this playback point"
    ),
    "chart_data": (
        "data visualization icon showing a {chart_type} chart",
        "displays analytics or statistics in {chart_type} format",
        "understand data trends or compare values visually"
    ),
    "tool_utility": (
        "tool icon shaped like a {tool_name}",
        "activates the {tool_name} tool or opens related options",
        "use the {tool_name} to fix, build, or configure something"
    ),
    "nature_weather": (
        "{element} icon with natural shape details",
        "indicates weather, environment, or a nature-themed feature",
        "check environmental conditions or toggle nature-related settings"
    ),
    "vehicle_transport": (
        "{vehicle} vehicle icon with standard body and wheel details",
        "opens {vehicle}-related tracking or transportation options",
        "manage, book, or track a {vehicle} trip or service"
    ),
    "animal": (
        "{animal} animal icon with simplified body outline",
        "represents an animal-themed feature or category",
        "access content or settings associated with {animal} animals"
    ),
    "food_drink": (
        "{food} icon with stylized shape and detail",
        "represents food-related content, a menu item, or a category",
        "browse food options or access a dining or nutrition feature"
    ),
    "sport_activity": (
        "{sport} icon representing the sport or physical activity",
        "opens a {sport} activity log or sports content",
        "track fitness, record a {sport} session, or view related stats"
    ),
    "brand_icon": (
        "logo icon for the {brand} brand or service",
        "links to or connects with {brand}",
        "visit the {brand} website or authenticate with this service"
    ),
    "generic": (
        "{name} icon with a distinctive outline shape",
        "activates the {name} feature or opens related settings",
        "use {name} functionality in the current context"
    ),
}

# Keyword-to-category mapping (checked in order, first match wins)
KEYWORD_CATEGORIES = [
    (["face-smile", "face-grin", "face-laugh", "face-sad", "face-frown",
      "face-meh", "face-surprise", "face-angry", "face-tired",
      "face-wink", "face-kiss"], "face_emoji"),
    (["circle-0","circle-1","circle-2","circle-3","circle-4","circle-5",
      "circle-6","circle-7","circle-8","circle-9"], "circle_variant"),
    (["square-0","square-1","square-2","square-3","square-4","square-5",
      "square-6","square-7","square-8","square-9"], "shape_symbol"),
]

WORD_CATEGORY_MAP = {
    # Animals
    "cat": "animal", "dog": "animal", "horse": "animal", "fish": "animal",
    "bird": "animal", "crow": "animal", "dove": "animal", "dragon": "animal",
    "frog": "animal", "hippo": "animal", "kiwi": "animal", "locust": "animal",
    "mosquito": "animal", "otter": "animal", "shrimp": "animal", "spider": "animal",
    "worm": "animal", "whale": "animal", "cow": "animal", "snake": "animal",
    "paw": "animal", "feather": "animal", "claws": "animal",
    # Food & Drink
    "apple": "food_drink", "bacon": "food_drink", "beer": "food_drink",
    "bowl": "food_drink", "bread": "food_drink", "cake": "food_drink",
    "candy": "food_drink", "carrot": "food_drink", "cheese": "food_drink",
    "coffee": "food_drink", "cookie": "food_drink", "corn": "food_drink",
    "croissant": "food_drink", "egg": "food_drink", "fish": "food_drink",
    "hotdog": "food_drink", "ice-cream": "food_drink", "lemon": "food_drink",
    "martini": "food_drink", "mug": "food_drink", "pepper": "food_drink",
    "pizza": "food_drink", "pretzel": "food_drink", "salad": "food_drink",
    "shrimp": "food_drink", "stroopwafel": "food_drink", "turkey": "food_drink",
    "utensils": "food_drink", "wheat": "food_drink", "wine": "food_drink",
    "seedling": "food_drink",
    # Sports
    "baseball": "sport_activity", "basketball": "sport_activity",
    "billiards": "sport_activity", "bowling": "sport_activity",
    "dumbbell": "sport_activity", "football": "sport_activity",
    "futbol": "sport_activity", "golf": "sport_activity",
    "hockey": "sport_activity", "person-skiing": "sport_activity",
    "person-swimming": "sport_activity", "person-biking": "sport_activity",
    "table-tennis": "sport_activity", "volleyball": "sport_activity",
    "ski": "sport_activity", "swimming": "sport_activity",
    "running": "sport_activity",
    # Vehicles
    "car": "vehicle_transport", "truck": "vehicle_transport",
    "bus": "vehicle_transport", "bicycle": "vehicle_transport",
    "plane": "vehicle_transport", "helicopter": "vehicle_transport",
    "ship": "vehicle_transport", "train": "vehicle_transport",
    "tractor": "vehicle_transport", "sailboat": "vehicle_transport",
    "motorcycle": "vehicle_transport", "taxi": "vehicle_transport",
    "ambulance": "vehicle_transport", "ferry": "vehicle_transport",
    "rocket": "vehicle_transport",
    # Nature
    "sun": "nature_weather", "moon": "nature_weather", "cloud": "nature_weather",
    "rainbow": "nature_weather", "snow": "nature_weather", "wind": "nature_weather",
    "tornado": "nature_weather", "volcano": "nature_weather",
    "mountain": "nature_weather", "tree": "nature_weather", "leaf": "nature_weather",
    "flower": "nature_weather", "seedling": "nature_weather",
    "star-and-crescent": "nature_weather",
    # Buildings
    "building": "building_structure", "castle": "building_structure",
    "church": "building_structure", "city": "building_structure",
    "hospital": "building_structure", "hotel": "building_structure",
    "mosque": "building_structure", "store": "building_structure",
    "synagogue": "building_structure", "temple": "building_structure",
    "warehouse": "building_structure",
    # Tools
    "hammer": "tool_utility", "wrench": "tool_utility", "screwdriver": "tool_utility",
    "axe": "tool_utility", "saw": "tool_utility", "drill": "tool_utility",
    "toolbox": "tool_utility", "ruler": "tool_utility", "compass": "tool_utility",
    "magnet": "tool_utility", "anchor": "tool_utility",
    # Charts/Data
    "chart": "chart_data", "diagram": "chart_data", "graph": "chart_data",
}


def to_label(words):
    """Convert a list of icon name words to a human-readable label."""
    special = {
        "xmark": "X Mark", "fa": "", "2": "Two", "3": "Three", "4": "Four",
        "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine",
        "0": "Zero", "1": "One", "xs": "Extra Small", "sm": "Small",
        "lg": "Large", "xl": "Extra Large", "2xl": "Double Extra Large",
        "lt": "Left", "rt": "Right", "ltr": "LTR", "rtl": "RTL",
        "and": "and", "of": "of", "in": "in", "with": "with",
    }
    result = []
    for w in words:
        if w in special:
            v = special[w]
            if v:
                result.append(v)
        elif len(w) <= 2 and w.isalpha():
            result.append(w.upper())
        else:
            result.append(w[0].upper() + w[1:] if w else "")
    label = " ".join(result).strip()
    return f"{label} icon" if label else "Icon"


def classify_icon(name, words):
    """Return a category key for the icon."""
    for prefixes, cat in KEYWORD_CATEGORIES:
        if name in prefixes:
            return cat

    # Check whole name
    if name.startswith("face-"):
        return "face_emoji"
    if name.startswith("circle-") and len(words) >= 2:
        return "circle_variant"
    if name.startswith("square-") and len(words) >= 2:
        return "shape_symbol"
    if name.startswith("person-"):
        return "person_figure"

    # Numbered family icons — must come before word-by-word loop so a trailing
    # digit doesn't mis-trigger the number_letter path.
    _NUMBERED_FAMILIES = [
        ("signal-alt-", "signal_strength"),
        ("signal-",     "signal_strength"),
        ("battery-",    "battery_level"),
        ("temperature-","temperature_level"),
        ("hourglass-",  "hourglass_state"),
        ("tally-",      "tally_marks"),
        ("wifi-",       "wifi_strength"),
        ("transporter-","transporter_state"),
    ]
    for prefix, cat in _NUMBERED_FAMILIES:
        if name.startswith(prefix) and name[len(prefix):].isdigit():
            return cat

    # Word-by-word category map
    for w in words:
        if w in WORD_CATEGORY_MAP:
            return WORD_CATEGORY_MAP[w]

    # Only classify as number_letter for truly standalone character icons
    # (fa-a…fa-z, fa-0…fa-9, fa-00, fa-100).  Multi-word names like
    # fa-x-ray or fa-arrows-h must NOT trigger here.
    if len(words) == 1:
        w = words[0]
        if w.isdigit() or (w.isalpha() and len(w) <= 3):
            return "number_letter"

    # Pattern-based
    if "arrow" in words:
        return "arrow_direction"
    if any(w in words for w in ["file", "document", "page"]):
        return "file_document"
    if any(w in words for w in ["chart", "graph", "diagram"]):
        return "chart_data"

    return "generic"


def make_metadata_from_name(class_name):
    """
    Generate semantic metadata for an icon by name when not in the curated dict.
    Returns (label, appearanceId, functionalityId, intentId).
    """
    name = class_name[3:]  # strip 'fa-'
    words = name.split("-")
    label = to_label(words)
    name_readable = label.replace(" icon", "").lower()
    category = classify_icon(name, words)

    if category == "face_emoji":
        expr = " ".join(words[1:]) if len(words) > 1 else "neutral"
        return (
            label,
            f"face with {expr} expression",
            f"inserts a {expr} emoji reaction or sentiment indicator",
            f"express a {expr} feeling or add an emotional response to a message"
        )

    if category == "circle_variant":
        inner = " ".join(words[1:]) if len(words) > 1 else "symbol"
        return (
            label,
            f"circle with {inner}",
            f"represents a circular {inner} indicator or action trigger",
            f"interact with or acknowledge a {inner}-related notification or state"
        )

    if category == "person_figure":
        detail = " ".join(words[1:]).replace("-", " ") if len(words) > 1 else "standing"
        return (
            label,
            f"person silhouette {detail}",
            f"opens a user or profile view showing {detail} status",
            f"manage a person's {detail} information or take a related action"
        )

    if category == "arrow_direction":
        dirs = [w for w in words if w in ("left","right","up","down","up-left","up-right","down-left","down-right")]
        direction = dirs[0] if dirs else "directional"
        shape = "curved" if "turn" in words or "rotate" in words else "straight"
        return (
            label,
            f"{shape} arrow pointing {direction}",
            f"navigates or moves content in the {direction} direction",
            f"go {direction}, navigate to the {direction} item, or shift the selected element"
        )

    if category == "building_structure":
        btype = words[0] if words else "building"
        return (
            label,
            f"{btype} building",
            f"opens location information or navigates to a {btype}",
            f"find or navigate to a {btype} location or facility"
        )

    if category == "shape_symbol":
        shape = words[0] if words else "shape"
        return (
            label,
            f"{shape} shape",
            f"represents a geometric marker or visual selection indicator",
            f"use this {shape} shape to mark, select, or visually organize content"
        )

    if category == "number_letter":
        char = words[0] if words else "character"
        if char.isalpha() and len(char) == 1:
            return (
                label,
                f"bold uppercase letter {char.upper()}",
                f"letter {char.upper()} as a text label or identifier",
                f"label or badge content with the letter {char.upper()}"
            )
        else:
            return (
                label,
                f"numeral {char}",
                f"numeric label or count {char}",
                f"display or label content with the number {char}"
            )

    if category == "signal_strength":
        alt = "alt" in words
        total = 4 if alt else 5
        n = int(words[-1]) if words[-1].isdigit() else 1
        strength = "minimal" if n == 1 else "weak" if n == 2 else "moderate" if n == 3 else "good"
        return (
            label,
            f"{total} signal bars with {n} bar{'s' if n > 1 else ''} filled",
            f"signal strength level {n} of {total}",
            f"indicate {strength} signal strength"
        )

    if category == "battery_level":
        n = int(words[-1]) if words[-1].isdigit() else 0
        descs = ["completely empty", "one quarter charged", "half charged",
                 "three quarters charged", "nearly full"]
        strength = ["critically low", "low", "moderate", "high", "high"]
        desc = descs[n] if n < len(descs) else "partially charged"
        return (
            label,
            f"rectangular battery outline {desc}",
            f"battery charge level {n} of {len(descs) - 1}",
            f"indicate {strength[n] if n < len(strength) else 'moderate'} battery level"
        )

    if category == "temperature_level":
        n = int(words[-1]) if words[-1].isdigit() else 0
        total = 4
        pct = n * 100 // total
        return (
            label,
            f"thermometer with fill at {pct} percent level",
            f"temperature gauge level {n} of {total}",
            f"indicate {'cold' if n <= 1 else 'moderate' if n <= 2 else 'warm'} temperature reading"
        )

    if category == "hourglass_state":
        n = int(words[-1]) if words[-1].isdigit() else 1
        states = {1: "sand mostly in upper chamber", 2: "sand equally split between chambers",
                  3: "sand mostly in lower chamber"}
        desc = states.get(n, "sand midway through")
        return (
            label,
            f"hourglass with {desc}",
            f"hourglass timer at stage {n} of 3",
            f"indicate time passing or a pending state"
        )

    if category == "tally_marks":
        n = int(words[-1]) if words[-1].isdigit() else 1
        return (
            label,
            f"{n} vertical tally mark{'s' if n > 1 else ''} in a row",
            f"tally count of {n}",
            f"represent a count or score of {n}"
        )

    if category == "wifi_strength":
        n = int(words[-1]) if words[-1].isdigit() else 1
        total = 3
        return (
            label,
            f"{total} wifi arcs with {n} arc{'s' if n > 1 else ''} filled",
            f"wifi signal strength {n} of {total}",
            f"indicate {'weak' if n == 1 else 'moderate'} wifi signal"
        )

    if category == "transporter_state":
        n = int(words[-1]) if words[-1].isdigit() else 1
        return (
            label,
            f"person silhouette dissolving into particles stage {n}",
            f"transporter beam animation frame {n}",
            f"indicate teleportation or sci-fi transport in progress"
        )

    if category == "file_document":
        ftype = " ".join(w for w in words if w not in ("file","document","page")) or "general"
        return (
            label,
            f"{ftype} document",
            f"opens, creates, or manages a {ftype} file or document",
            f"work with a {ftype} document in the file system"
        )

    if category == "chart_data":
        ctype = " ".join(w for w in words if w not in ("chart","graph","diagram")) or "data"
        return (
            label,
            f"{ctype} chart",
            f"displays {ctype} analytics or statistics in visual chart form",
            f"understand {ctype} data trends or compare values at a glance"
        )

    if category == "tool_utility":
        tool = words[0] if words else "tool"
        return (
            label,
            f"{tool}",
            f"activates the {tool} utility or opens maintenance settings",
            f"use the {tool} to fix, build, or configure a component"
        )

    if category == "nature_weather":
        elem = words[0] if words else "natural element"
        return (
            label,
            f"{elem}",
            f"indicates a weather condition or nature-themed feature",
            f"check environmental conditions or toggle a {elem}-related setting"
        )

    if category == "vehicle_transport":
        vehicle = words[0] if words else "vehicle"
        return (
            label,
            f"{vehicle}",
            f"opens {vehicle} tracking, booking, or transportation options",
            f"manage or track a {vehicle} trip, route, or service"
        )

    if category == "animal":
        animal = words[0] if words else "animal"
        return (
            label,
            f"{animal}",
            f"represents an {animal}-related category or themed feature",
            f"access content or settings associated with {animal}s"
        )

    if category == "food_drink":
        food = " ".join(words) if words else "food item"
        return (
            label,
            f"{food}",
            f"represents a food category, menu item, or nutrition feature",
            f"browse food options or access a dining, recipe, or nutrition feature"
        )

    if category == "sport_activity":
        sport = " ".join(words) if words else "sport"
        return (
            label,
            f"{sport}",
            f"opens a {sport} activity log, score, or sports content",
            f"track a {sport} session, view scores, or explore related fitness content"
        )

    if category == "brand_icon":
        brand = name_readable
        return (
            label,
            f"{brand} logo",
            f"links to or authenticates with the {brand} service or platform",
            f"visit {brand} or connect this account to the {brand} service"
        )

    # Generic fallback
    return (
        label,
        f"{name_readable} icon",
        f"activates the {name_readable} feature or opens related settings",
        f"use {name_readable} functionality in the current working context"
    )


def load_overrides():
    """Load LLM-generated metadata improvements from metadata_overrides.json."""
    overrides_path = os.path.join(os.path.dirname(__file__), 'metadata_overrides.json')
    if os.path.exists(overrides_path):
        with open(overrides_path) as f:
            return json.load(f)
    return {}

METADATA_OVERRIDES = load_overrides()


def get_metadata(class_name, is_brand=False):
    """Return (label, appearanceId, functionalityId, intentId) for a class name."""
    name = class_name[3:]  # strip 'fa-'

    if is_brand:
        words = name.split("-")
        label = to_label(words)
        brand_name = label.replace(" icon", "").strip()
        # Clean up common brand name suffixes for readability
        brand_readable = brand_name.lower()
        return (
            label,
            f"official logo icon for {brand_readable} with brand-distinctive shape and design",
            f"links to or authenticates with the {brand_readable} service or platform",
            f"visit {brand_readable} or connect this account to the {brand_readable} service"
        )

    # LLM-generated overrides take priority over everything (including curated)
    if class_name in METADATA_OVERRIDES:
        ov = METADATA_OVERRIDES[class_name]
        words = name.split("-")
        label = to_label(words)
        return label, ov["appearanceId"], ov["functionalityId"], ov["intentId"]

    if name in CURATED_METADATA:
        label_text, appearance, functionality, intent = CURATED_METADATA[name]
        label = f"{label_text} icon" if not label_text.lower().endswith(" icon") else label_text
        return label, appearance, functionality, intent

    if class_name in METADATA_OVERRIDES:
        ov = METADATA_OVERRIDES[class_name]
        words = name.split("-")
        label = to_label(words)
        return label, ov["appearanceId"], ov["functionalityId"], ov["intentId"]

    return make_metadata_from_name(class_name)


# ─── Deduplication ────────────────────────────────────────────────────────────

def deduplicate_icons(icons, family_prefix):
    """
    Deduplicate icons by primary codepoint.
    Returns dict: primary_cp → (canonical_class, primary_cp, secondary_cp)
    Canonical class: shortest name, then alphabetically first.
    """
    groups = {}  # primary_cp → list of class names
    cp_map = {}  # primary_cp → (primary_cp, secondary_cp)

    for cls, (primary_cp, secondary_cp) in icons.items():
        if primary_cp not in groups:
            groups[primary_cp] = []
            cp_map[primary_cp] = (primary_cp, secondary_cp)
        groups[primary_cp].append(cls)

    result = {}
    for primary_cp, classes in groups.items():
        # Choose canonical: shortest name, then alphabetically first
        canonical = sorted(classes, key=lambda c: (len(c), c))[0]
        result[primary_cp] = (canonical, cp_map[primary_cp][0], cp_map[primary_cp][1])

    return result


# ─── Seeded shuffle ───────────────────────────────────────────────────────────

def seeded_shuffle(items, seed):
    """Deterministically shuffle items using a simple PRNG (Fisher-Yates)."""
    result = list(items)
    state = seed & 0xFFFFFFFF
    for i in range(len(result) - 1, 0, -1):
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        j = state % (i + 1)
        result[i], result[j] = result[j], result[i]
    return result


# ─── Main generation ──────────────────────────────────────────────────────────

def build_manifest(non_brand_deduped, brand_deduped, font_cps):
    """
    Build base metadata list and ordered manifest entries.

    non_brand_deduped: dict primary_cp → (canonical_class, primary_cp, secondary_cp)
    brand_deduped: same for brands
    font_cps: dict font_file_name → set of codepoints
    """

    # Build non-brand icon groups with style variants
    non_brand_groups = []
    for primary_cp, (canonical_class, pcp, scp) in sorted(non_brand_deduped.items()):
        visual_key = f"classic:{primary_cp:x}"
        label, appearance, functionality, intent = get_metadata(canonical_class)

        base = {
            "visualKey": visual_key,
            "iconClass": canonical_class,
            "label": label,
            "appearanceId": appearance,
            "functionalityId": functionality,
            "intentId": intent,
        }

        variants = []
        for style in NON_BRAND_STYLES:
            font_file = style["fontFile"]
            cps = font_cps.get(font_file, set())
            if pcp in cps:
                variants.append({
                    **base,
                    "styleName": style["name"],
                    "styleClass": style["className"],
                })

        if variants:
            non_brand_groups.append({"base": base, "variants": variants})

    # Build brand icon groups
    brand_groups = []
    for primary_cp, (canonical_class, pcp, scp) in sorted(brand_deduped.items()):
        visual_key = f"brands:{primary_cp:x}"
        label, appearance, functionality, intent = get_metadata(canonical_class, is_brand=True)

        cps = font_cps.get(BRAND_STYLE["fontFile"], set())
        if pcp not in cps:
            continue

        base = {
            "visualKey": visual_key,
            "iconClass": canonical_class,
            "label": label,
            "appearanceId": appearance,
            "functionalityId": functionality,
            "intentId": intent,
        }

        brand_groups.append({
            "base": base,
            "variants": [{
                **base,
                "styleName": BRAND_STYLE["name"],
                "styleClass": BRAND_STYLE["className"],
            }]
        })

    # Shuffle all groups deterministically
    all_groups = non_brand_groups + brand_groups
    all_shuffled = seeded_shuffle(all_groups, seed=42)
    nb_shuffled = [g for g in all_shuffled if g["base"]["visualKey"].startswith("classic:")]

    # Build manifest using pass-based interleaving
    # Pass 0: all groups (brand + non-brand), each contributing their first style variant
    # Passes 1-15: non-brand groups only, each contributing subsequent style variants
    # This guarantees no duplicate visualKey per page because:
    # - Each pass has 3319+ entries >> page size of 40
    # - Within a pass, each group appears exactly once

    manifest = []
    pass_sizes = []

    # Pass 0
    pass0 = [g["variants"][0] for g in all_shuffled]
    manifest.extend(pass0)
    pass_sizes.append(len(pass0))

    # Passes 1-15 (non-brand only)
    ROTATION = 1000  # rotate order per pass to avoid cross-boundary duplicates
    n_nb = len(nb_shuffled)
    for v in range(1, 16):
        rot = (v - 1) * ROTATION % n_nb
        rotated = nb_shuffled[rot:] + nb_shuffled[:rot]
        passv = [g["variants"][v] for g in rotated if len(g["variants"]) > v]
        manifest.extend(passv)
        pass_sizes.append(len(passv))

    # Validate: check for duplicate visualKey per page
    total = len(manifest)
    conflicts = 0
    for page_start in range(0, total, ICONS_PER_PAGE):
        page = manifest[page_start:page_start + ICONS_PER_PAGE]
        keys = [e["visualKey"] for e in page]
        if len(keys) != len(set(keys)):
            from collections import Counter
            dupes = [k for k, c in Counter(keys).items() if c > 1]
            conflicts += len(dupes)

    if conflicts > 0:
        print(f"  WARNING: {conflicts} duplicate visualKey conflicts found, fixing...")
        manifest = fix_conflicts(manifest)

    base_metadata = [g["base"] for g in all_shuffled]
    brand_bases = [g["base"] for g in brand_groups]
    all_bases = [g["base"] for g in non_brand_groups] + brand_bases

    return all_bases, manifest, non_brand_groups, brand_groups


def fix_conflicts(manifest):
    """Swap out duplicate visualKeys within pages."""
    n = len(manifest)
    for page_start in range(0, n, ICONS_PER_PAGE):
        page_end = min(page_start + ICONS_PER_PAGE, n)
        page = manifest[page_start:page_end]
        seen = {}
        for i, entry in enumerate(page):
            key = entry["visualKey"]
            if key in seen:
                # Find a swap candidate after page_end with a different key
                for j in range(page_end, n):
                    cand_key = manifest[j]["visualKey"]
                    if cand_key not in seen and cand_key not in {e["visualKey"] for e in page}:
                        manifest[page_start + i], manifest[j] = manifest[j], manifest[page_start + i]
                        seen[cand_key] = page_start + i
                        break
            else:
                seen[key] = page_start + i
    return manifest


# ─── JS output ────────────────────────────────────────────────────────────────

def escape_js_string(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def write_base_metadata(base_metadata, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["// Auto-generated by generate_fontawesome_manifest.py — do not edit",
             "// One entry per unique visual icon (deduplicated by glyph codepoint)",
             "export const fontawesomeBaseMetadata = ["]
    for entry in base_metadata:
        lines.append("  {")
        for k, v in entry.items():
            lines.append(f'    {k}: "{escape_js_string(v)}",')
        lines.append("  },")
    lines.append("];")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_manifest(manifest, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    page_count = math.ceil(len(manifest) / ICONS_PER_PAGE)
    lines = ["// Auto-generated by generate_fontawesome_manifest.py — do not edit",
             f"export const iconsPerPage = {ICONS_PER_PAGE};",
             f"export const pageCount = {page_count};",
             "export const fontawesomeManifest = ["]
    for entry in manifest:
        lines.append("  {")
        for k, v in entry.items():
            lines.append(f'    {k}: "{escape_js_string(v)}",')
        lines.append("  },")
    lines.append("];")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_urls(page_count, path):
    with open(path, "w", encoding="utf-8") as f:
        for i in range(1, page_count + 1):
            f.write(f"/?page={i}\n")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=== Font Awesome Pro 6.7.2 Manifest Generator ===\n")

    # Parse CSS files
    print("Parsing fontawesome.css ...")
    fa_css = os.path.join(CSS_DIR, "fontawesome.css")
    non_brand_icons = parse_icon_css(fa_css)
    print(f"  Found {len(non_brand_icons)} non-brand CSS class definitions")

    print("Parsing brands.css ...")
    brands_css = os.path.join(CSS_DIR, "brands.css")
    brand_icons = parse_icon_css(brands_css, brands=True)
    print(f"  Found {len(brand_icons)} brand CSS class definitions")

    # Deduplicate
    print("Deduplicating by visual glyph identity ...")
    non_brand_deduped = deduplicate_icons(non_brand_icons, "classic")
    brand_deduped = deduplicate_icons(brand_icons, "brands")
    print(f"  {len(non_brand_deduped)} unique non-brand visual icons")
    print(f"  {len(brand_deduped)} unique brand visual icons")

    # Parse TTF cmap tables
    print("Parsing TTF cmap tables ...")
    font_cps = {}
    for style in NON_BRAND_STYLES:
        ttf_path = os.path.join(FONT_DIR, style["fontFile"])
        if os.path.exists(ttf_path):
            font_cps[style["fontFile"]] = read_cmap_codepoints(ttf_path)
            print(f"  {style['fontFile']}: {len(font_cps[style['fontFile']])} codepoints")
        else:
            print(f"  WARNING: {ttf_path} not found!")
            font_cps[style["fontFile"]] = set()

    brand_ttf = os.path.join(FONT_DIR, BRAND_STYLE["fontFile"])
    if os.path.exists(brand_ttf):
        font_cps[BRAND_STYLE["fontFile"]] = read_cmap_codepoints(brand_ttf)
        print(f"  {BRAND_STYLE['fontFile']}: {len(font_cps[BRAND_STYLE['fontFile']])} codepoints")
    else:
        print(f"  WARNING: {brand_ttf} not found!")
        font_cps[BRAND_STYLE["fontFile"]] = set()

    # Build manifest
    print("\nBuilding manifest ...")
    base_metadata, manifest, nb_groups, brand_groups = build_manifest(
        non_brand_deduped, brand_deduped, font_cps
    )

    total_entries = len(manifest)
    page_count = math.ceil(total_entries / ICONS_PER_PAGE)

    print(f"\n=== Validation ===")
    print(f"  Non-brand visual icons: {len(nb_groups)}")
    print(f"  Brand visual icons:     {len(brand_groups)}")
    print(f"  Total visual icons:     {len(nb_groups) + len(brand_groups)}")
    nb_variants = sum(len(g['variants']) for g in nb_groups)
    b_variants = sum(len(g['variants']) for g in brand_groups)
    print(f"  Non-brand examples:     {nb_variants}")
    print(f"  Brand examples:         {b_variants}")
    print(f"  Total examples:         {total_entries}")
    print(f"  Pages (ceil/40):        {page_count}")

    # Validate no duplicate visualKey per page
    violations = 0
    for page_num in range(1, page_count + 1):
        start = (page_num - 1) * ICONS_PER_PAGE
        page = manifest[start:start + ICONS_PER_PAGE]
        keys = [e["visualKey"] for e in page]
        if len(keys) != len(set(keys)):
            violations += 1
            print(f"  VIOLATION on page {page_num}: duplicate visualKey")

    if violations == 0:
        print("  No duplicate visualKey violations ✓")

    # Validate metadata quality
    missing_fields = 0
    for entry in base_metadata:
        for field in ("label", "appearanceId", "functionalityId", "intentId"):
            if not entry.get(field):
                missing_fields += 1
    print(f"  Missing metadata fields: {missing_fields}")

    # Write output files
    print(f"\nWriting output files ...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    base_path = os.path.join(OUTPUT_DIR, "fontawesomeBaseMetadata.js")
    manifest_path = os.path.join(OUTPUT_DIR, "fontawesomeManifest.js")
    urls_path = os.path.join(BASE_DIR, "urls.txt")

    write_base_metadata(base_metadata, base_path)
    print(f"  Wrote {base_path}")

    write_manifest(manifest, manifest_path)
    print(f"  Wrote {manifest_path}")

    write_urls(page_count, urls_path)
    print(f"  Wrote {urls_path} ({page_count} URLs)")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
