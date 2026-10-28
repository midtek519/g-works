G-VIEW — G-Whiz's Canvas course organizer
Version 0.2.1

INSTALL
Open G-Works and click G-View beneath G-Whiz. The installation helper opens
Chrome extensions and gives you the permanent bundled extension folder.
Enable Developer mode, choose Load unpacked, and select that folder. Reload
Canvas's All Courses page. Pin G-View in Chrome's Extensions menu if desired;
clicking its toolbar icon opens https://rutgers.instructure.com/courses.

USE
The five main accordions are:
1. Other instructors' course pages
2. My course pages
3. Instructor sites
4. All-Sections sites
5. Other

Each contains separate course groups, then semesters, newest first. The course
colors are crimson for 135, blue for 151/152/251, teal for 130, purple for 250,
and gray for other courses. Course labels remain visible alongside the colors.
Click a color chip to filter to that course group; click it again to show all.
The chips begin with 130 on the left. Drag the grip beside a category title, or
use its up/down buttons, to reorder categories. The order is saved locally and
included in label backups. Reset clears filters while keeping the chosen order.
Search by name, section, semester, Canvas role, or your own note. Stars pin rows
within their course group; Pinned only filters the same five accordions.
Click Organize to correct a category, display name, semester, or note. Clearing
an override returns to the local teaching-history default when available.

Canvas roles do not reliably identify the actual instructor. This installation
can supply an optional local teaching-history profile through the G-Whiz helper.
Without a profile, section pages start in Other instructors' course pages and
can be moved with Organize. Existing explicit category choices take priority.
Default Term pages use recognizable semester text in the title where possible.
Duplicate enrollments with the same course ID share one row and keep all roles.

Original Canvas view exposes the original tables and favorite controls. Local
pins are separate from Canvas favorites. Backup / help exports or imports your
labels and pins. Import merges by course ID and replaces matching local values.

DATA AND UPDATES
Settings use chrome.storage.local in this Chrome profile, scoped to the Canvas
hostname. No API token, server, analytics, or external background requests. The
extension reads the course rows already loaded on All Courses. Individual
course pages are excluded by the runtime path check. Canvas records are not
changed. Course links are retained only when Canvas actually provides them.

G-Works packages only the extension's reviewed program and icon files. Optional
local-defaults.json is staged by setup from the app's Data/G-View folder and is
excluded from distributable packages. The extension copies its defaults into
local Chrome storage without replacing existing labels, pins, or overrides.
Personal labels stay in Chrome. After an update, click Reload on G-View's card in
chrome://extensions, then reload Canvas. Keep this folder in place. Uninstalling
the extension clears its settings; export labels before uninstalling.

Icon: original G-Whiz crimson course-folder mark with a G, with a matching launcher glyph.
Editable source: icons/source.svg. Toolbar PNGs: 16, 20, 24, 32, 48, 64, 128 px.

https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world#load-unpacked
