Flux Electro Mechanical - Secure Flask Backend

New additions
- admin login
- password hashing
- inquiry dashboard
- search and filter on inquiries
- status update workflow
- protected file downloads
- simple console notification when a new inquiry arrives

Default login
- Email: solutions@fluxelectromechanical.enginner.et
- Password: ChangeMe123!

Important
- Change the admin password before production.
- Change FLASK_SECRET_KEY before production.
- This version prints a notification to the server console when a new inquiry arrives.
- Real email alerts are not configured yet because they require your SMTP details or mail provider.

How to run
1. Install Python 3.10+
2. Run:
   pip install -r requirements.txt
3. Optional:
   copy .env.example values into your environment
4. Start:
   python app.py
5. Open:
   http://127.0.0.1:5000

Admin routes
- /admin/login
- /admin
- /admin/inquiries
- /admin/inquiries/<id>

Suggested next upgrade
- real email notifications with Gmail SMTP, Zoho, cPanel mail, or SendGrid


Email alerts added
- SMTP-based real email notification is now built in
- Every new quote request can send an email alert to your inbox
- If SMTP is not configured, the app still works and falls back to console logging

To enable email alerts
1. Set SMTP_HOST
2. Set SMTP_PORT
3. Set SMTP_USERNAME
4. Set SMTP_PASSWORD
5. Set MAIL_FROM
6. Set MAIL_TO

Example
- Gmail SMTP host: smtp.gmail.com
- Port: 587
- Use an app password, not your normal Gmail password, if your provider requires it

Notes
- The uploaded file itself is not attached to the notification email
- The email includes the uploaded filename and all inquiry details
- Attachments can still be viewed in the admin panel after login


Integrated version
- advanced public website merged with the secure Flask backend
- public routes: /, /about, /services, /projects, /contact
- quote form submits into the database with file upload support
- admin login, dashboard, inquiry list, and status updates remain included


Client membership added
- client registration
- client login/logout
- member-only page at /members
- member-only downloadable resources
- registered clients can see quote requests submitted with their email address

Member routes
- /members/register
- /members/login
- /members/logout
- /members


Latest access changes
- quote submission now requires member login
- admin navigation is hidden from public visitors
- member login is the main visible entry point
- if a logged-in member email also exists as an admin, the system automatically opens full admin privileges


Access control update
- quote submission now requires member login
- admin link is hidden from the public website navigation
- member login is now the main entry point
- if a member logs in with an email that also exists in the admins table, full admin privileges are enabled automatically


Admin login fix
- the member login page now accepts direct admin login
- admins no longer need a separate client/member account to open the admin dashboard
- use the member login page with the admin email and password


Strong upgrade added
- admin can create member accounts from dashboard
- admin can upload member-only files from dashboard
- clients can edit their profile
- password reset by email is included
- reset links use PUBLIC_BASE_URL from environment settings


Project image upload upgrade added
- admin can now upload project images directly from the dashboard
- uploaded images are stored in the project_images folder
- public /projects page displays uploaded project images automatically
- image URL field remains available as an optional fallback


Projects table fix
- schema.sql now includes the missing projects table
- on next app start, init_db() will create the projects table automatically

If you still see "no such table: projects":
1. stop the Flask app
2. restart it with python app.py
3. if needed, delete the old instance/flux_website.sqlite3 file and start again


Final hardening updates
- runtime table creation added so existing databases do not fail with missing projects/password reset tables
- project image cleanup added on project delete
- admin project workflow finalized
- safer startup behavior for older database files

Recommended final steps before deployment
1. change FLUX_ADMIN_PASSWORD
2. set FLASK_SECRET_KEY
3. configure SMTP settings
4. set PUBLIC_BASE_URL to your live domain
5. run once locally and verify:
   - member login
   - admin login via member login
   - quote submission
   - password reset
   - project create/edit/delete with image upload


PostgreSQL migration upgrade added
- app now supports PostgreSQL through DATABASE_URL
- SQLite remains supported for local/simple use
- psycopg added for PostgreSQL connections
- Render config updated with managed PostgreSQL
- runtime table creation works for PostgreSQL too

How it works
- If DATABASE_URL is set to a postgres connection string, the app uses PostgreSQL
- If DATABASE_URL is not set, the app falls back to SQLite

Recommended production setup
- Use PostgreSQL in production
- Keep SQLite only for local testing

Important
- Existing SQLite data is not automatically copied into PostgreSQL
- This upgrade prepares the app for PostgreSQL; data migration would be a separate step if needed


PostgreSQL placeholder fix
- fixed remaining startup queries that mixed SQLite and PostgreSQL placeholders
- ensure_default_admin now supports both SQLite and PostgreSQL correctly
- ensure_sample_member_resource now supports both SQLite and PostgreSQL correctly
- startup prints whether the app is using SQLite or PostgreSQL


Final PostgreSQL startup fix
- fixed ensure_default_admin() for both SQLite and PostgreSQL
- fixed ensure_sample_member_resource() for both SQLite and PostgreSQL
- startup now prints Database mode


PostgreSQL dashboard fix
- fixed admin dashboard count queries for PostgreSQL dict-style rows
- removed KeyError: 0 caused by tuple-style indexing on PostgreSQL result rows

Forced dashboard count patch applied for PostgreSQL rows.


Full branding upgrade added
- uploaded FLUX logo integrated into the website
- favicon added from the logo
- global black and gold luxury style applied
- admin and public pages now follow luxury brand colors
- buttons, cards, tables, hero sections, footer, forms, and navigation updated to match the new brand

Refined luxury styling added: reduced harsh contrast, softer gold, cleaner shadows, more balanced dark surfaces.

Blue luxury comfort update applied: charcoal blue backgrounds, softer gold accents, calmer contrast, engineering-style premium palette.

Professional polish added: improved spacing, typography, button sizing, card consistency, table styling, and cleaner responsive presentation.


Staff members upgrade added
- admin can create staff members
- automatic staff ID generation added
- admin can update and delete staff members
- public staff page added
- staff admin section added to dashboard
- staff code format: FLX-STF-001, FLX-STF-002, ...


PostgreSQL staff fix
- fixed staff_members table creation for PostgreSQL
- removed SQLite AUTOINCREMENT syntax from PostgreSQL startup
- staff sample seed now works in both SQLite and PostgreSQL
- staff create, edit, and delete routes now support PostgreSQL correctly

Fixed PostgreSQL init: removed leftover AUTOINCREMENT staff table from PostgreSQL startup block.


Staff visibility and ID card upgrade
- public staff page removed from public navigation
- staff management is now admin-only
- print option added for each staff member
- branded printable ID card added with FLUX logo and premium design


Staff admin refinement
- removed duplicate Staff Admin links so only one remains in admin navigation
- added direct staff photo upload
- refined staff admin layout for cleaner management
- refined staff form with preview and upload guidance


ID card advanced upgrade
- added front and back card layout
- added visual verification grid based on staff token
- improved print presentation for more professional ID output

Fixed ID card template: removed unsupported Jinja ord filter from visual verification grid.


Final staff admin refinement
- removed duplicate Staff Admin links so only one remains in navigation
- refined the back side of the ID card to match the premium dark blue and gold front side


Equal print size refinement
- front and back staff ID cards now use the same fixed dimensions
- print layout now keeps both sides equal size
- improved print consistency for A4 landscape output

Front ID card overlap fix applied: reserved footer space and tightened front-side spacing.

Premium ID design applied: hologram accent, better footer layout, active chip moved top-right, cleaner spacing, stronger front/back balance.


Testimonials admin upgrade added
- admin testimonials page added
- create, update, delete testimonial form added
- homepage testimonials now load from the database
- dashboard testimonial count added

PostgreSQL fix applied for testimonials: removed executescript in PostgreSQL mode and fixed testimonial CRUD placeholders.

Step 1 PostgreSQL member fix: corrected admin create member email lookup and insert placeholders for PostgreSQL.

Step 2 PostgreSQL member fix: corrected indentation in admin_create_member dual-database email lookup.

Step 3 PostgreSQL member fix: repaired the full admin_create_member indentation block around existing member lookup.

Step 4 clean fix: repaired full admin_create_member block and normalized tabs to spaces in app.py.

Step 5 PostgreSQL resource fix: corrected member resource create/update/delete placeholders for PostgreSQL.

Step 6 PostgreSQL resource fix: corrected create member resource insert with category field for PostgreSQL placeholders.

Step 7 PostgreSQL projects fix: corrected project create, edit, delete, and project lookup placeholders for PostgreSQL.

Deployment package prepared with Procfile, runtime.txt, requirements.txt, Railway and Render configuration.
