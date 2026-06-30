# Acquacotta

## Why use Acquacotta?

Key Features
- Implements all features of the standard pomodoro technique (25 minute focus, 5 minuute short break, 15 minute long break)
- Provides 4 pre-set focus timers and 2 pre-set break timers (all configurable)
- Integrated timer with sliadable face to provide the same functionality as a physical tomato timer on your desk
- Seemlessly works with an external pomodoro timer sitting on your desk
- Free and open source [online service](https://acquacotta.crunchtools.com:8443) or use in a local container

Advanced Time Management:
- Weekly dashboard which helps you proactively tune how much you work and on which focus areas
- Set visual daily minutes goal to make sure you're getting enough pomodoros done each day, but not too many
- Custom Pomodoro types to ensure you're working on what you want to (Code, Customers, PTO, etc)
- Daily, Weekly, and Monthly graphical/visual reports to help you better focus your time
- Auto-start the next Pomodoro to avoid interruptions when in the flow state

Technical Features:
- Real, recorded ticking sound provides focus stimulation (Pavlov's Dogs)
- Uses an internal SQLite database by default
- Designed to run in a Podman/Docker container or use the free online service
- Seemlessly work between online and container using data and setting optionally saved in a private Google Sheet
- Responsive authors - feel free to file any and all issues [here](https://github.com/crunchtools/acquacotta/issues)

## The Story Behind the Soup

Acquacotta was created as fun project by a veteran of the Pomodoro Technique with over 20+ years of using this system from doing HPC work at NASA to Product Management for Podman, Red Hat Universal Base Image, and Red Hat Enterprise Linux 10 [LinkedIn](https://www.linkedin.com/in/fatherlinux/details/experience/). It could be said that Acquacotta was rigorously vibe coded (I know, it sounds like an oxymoron) using spec-kit, and a strict process for adding Features. The [constitution](https://github.com/crunchtools/acquacotta/blob/main/.specify/memory/constitution.md) and [feature specifications](https://github.com/crunchtools/acquacotta/blob/main/.specify/specs/000-baseline/spec.md) are transparently committed in the [Acquacotta Git repository](https://github.com/crunchtools/acquacotta). For 20+ years I have meticulously tracked my pomodoros, always analyzing the last four weeks. I have refined the Pomodoro technique into set of practices that not only give me focus, but also give me a sense of satisfaction and freedom. 

**Why the name?**

Acquacotta means "cooked water" in Italian—a traditional, hearty tomato soup. Since the Pomodoro technique is named after the tomato-shaped kitchen timer (tomato is *Pomodoro* in Italian), we felt a "complete meal" of a system—timer, automated logging, and powerful reporting—deserved a name that felt just as substantial.

# Getting Started
Every time a PR is merged, GitHub Actions builds and pushes a new version of the container to quay.io/crunchtools/acquacotta This container image is free to use.

## Self-Hosting

### Rootless

Just run:
```
podman run -id -p 443:443 --name acquacotta quay.io/crunchtools/acquacotta
```
Connect to the following URL (accept the auto-generated SSL certificate):
```
https://localhost:8443
```

### As root

Just run:
```
podman run -id -p 443:443 --name acquacotta quay.io/crunchtools/acquacotta
```
Connect to the following URL (accept the auto-generated SSL certificate):
```
https://localhost
```

## Free and Open Source Online Service

The free and open source service is always free to use. It's serving from the latest container image built in GitHub actions. The local SQLite database is shared, so do not save any sensitive information. If you require privacy with the online service, please use the Google Drive integration. You can always export it with the Export to CVS button under the Reports tab. The online service is configured to enable authentication for Googel Sheets (optional). You can migrate your data to a private Sheet, then use it locally with your own container if you like.
- https://acquacotta.crunchtools.com:8443



# Advanced Operations

## Running Without Podman/Docker

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GOOGLE_CLIENT_ID="your-client-id"
export GOOGLE_CLIENT_SECRET="your-client-secret"
export FLASK_SECRET_KEY="random-secret"

# Run
python app.py
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_CLIENT_ID` | Yes | OAuth Client ID from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | Yes | OAuth Client Secret from Google Cloud Console |
| `FLASK_SECRET_KEY` | Yes | Random string for session encryption |
| `FLASK_HOST` | No | Host to bind to (default: `127.0.0.1`, use `0.0.0.0` for container) |
| `CLEAR_CACHE_ON_START` | No | Clear SQLite cache on startup (default: `true`) |

## Data Storage

By default, your pomodoro data is stored in a SQLite database. The directory can be bind mounted into the container to give persistence to the data. You can also export it through the CSV button on the Reports tab. If you use the online service, this database is shared.
```
/data/acquacotta/pomodoros.db
```

If you optionally configure Google Drive, a Google Sheet will get created. You own and control your data. you can make backup copies, or analyze it with Gemini, etc:
- **Document Name**: Acquacotta - Pomodoro Tracker
- **Pomodoros Tab**: All your tracked pomodoros
- **Settings Tab**: Your app preferences

## Setup your service to accept Google Authentication

### Set Up Google Cloud Credentials (one-time, ~5 minutes)

Acquacotta uses Google Sheets to store your data. Each user needs to create their own Google Cloud credentials.

#### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top → "New Project"
3. Name it `Acquacotta` → Click "Create"
4. Make sure your new project is selected in the dropdown

#### Step 2: Enable Required APIs

1. Go to **APIs & Services** → **Library** (in the left sidebar)
2. Search for `Google Sheets API` → Click it → Click **Enable**
3. Search for `Google Drive API` → Click it → Click **Enable**

#### Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **External** → Click "Create"
3. Fill in the required fields:
   - App name: `Acquacotta`
   - User support email: *your email*
   - Developer contact email: *your email*
4. Click **Save and Continue**
5. On the "Scopes" page, click **Save and Continue** (no changes needed)
6. On the "Test users" page, click **Save and Continue**
7. Click **Back to Dashboard**

#### Step 4: Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. Application type: **Web application**
4. Name: `Acquacotta Web`
5. Under "Authorized redirect URIs", click **Add URI** and enter:
   ```
   http://localhost:5000/auth/callback
   ```
6. Click **Create**
7. A popup will show your **Client ID** and **Client Secret** - copy both!

### 2. Run with Podman/Docker

```bash
podman run -d --name acquacotta \
  --security-opt label=disable \
  --network host \
  -e GOOGLE_CLIENT_ID="your-client-id-here" \
  -e GOOGLE_CLIENT_SECRET="your-client-secret-here" \
  -e FLASK_SECRET_KEY="any-random-string-here" \
  quay.io/crunchtools/acquacotta:latest
```

Or build locally:

```bash
git clone https://github.com/crunchtools/acquacotta.git
cd acquacotta
podman build -t acquacotta .
podman run -d --name acquacotta \
  --security-opt label=disable \
  --network host \
  -e GOOGLE_CLIENT_ID="your-client-id-here" \
  -e GOOGLE_CLIENT_SECRET="your-client-secret-here" \
  -e FLASK_SECRET_KEY="any-random-string-here" \
  acquacotta
```

> **Note:** The `--security-opt label=disable` flag is needed on SELinux-enabled systems (Fedora, RHEL, CentOS).

Then open http://localhost:5000 in your browser.

### 3. Sign In

1. Open http://localhost:5000
2. Click "Sign in with Google"
3. Authorize the app to access Google Sheets
4. A new spreadsheet called "Acquacotta - Pomodoro Tracker" will be created in your Google Drive

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_CLIENT_ID` | Yes | OAuth Client ID from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | Yes | OAuth Client Secret from Google Cloud Console |
| `FLASK_SECRET_KEY` | Yes | Random string for session encryption |
| `FLASK_HOST` | No | Host to bind to (default: `127.0.0.1`, use `0.0.0.0` for container) |
| `CLEAR_CACHE_ON_START` | No | Clear SQLite cache on startup (default: `true`) |

## Running Without Docker

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GOOGLE_CLIENT_ID="your-client-id"
export GOOGLE_CLIENT_SECRET="your-client-secret"
export FLASK_SECRET_KEY="random-secret"

# Run
python app.py
```

## Data Storage

Your pomodoro data is stored in a Google Sheet in your own Google Drive:
- **Pomodoros tab**: All your tracked pomodoros
- **Settings tab**: Your app preferences

You own your data and can access/edit it directly in Google Sheets. Power users can:
- Make backups anytime
- Analyze patterns with LLMs
- Build custom reports
- Export to other tools

### Persisting the SQLite Cache (Optional)

Acquacotta uses SQLite as a local cache for fast reads, with Google Sheets as the persistent backend. By default, the cache is cleared on container restart and re-syncs from Google Sheets on login.

To persist the cache between restarts (avoiding re-sync delay):

```bash
podman run -d --name acquacotta \
  --network host \
  -v /path/on/host:/root/.local/share/acquacotta:Z \
  -e CLEAR_CACHE_ON_START=false \
  -e GOOGLE_CLIENT_ID="your-client-id-here" \
  -e GOOGLE_CLIENT_SECRET="your-client-secret-here" \
  -e FLASK_SECRET_KEY="any-random-string-here" \
  quay.io/crunchtools/acquacotta:latest
```

> **Note:** The `:Z` suffix is required on SELinux-enabled systems (Fedora, RHEL, CentOS) for bind mounts.

# Troubleshooting

### "Sign in with Google" button doesn't work

Make sure you've set the `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` environment variables when starting the container.

### "Access blocked: This app's request is invalid"

Your redirect URI doesn't match. In Google Cloud Console → Credentials → Your OAuth Client, make sure the Authorized redirect URI is exactly:
```
http://localhost:5000/auth/callback
```

### "Google hasn't verified this app" warning

This is normal for personal OAuth apps. Click "Advanced" → "Go to Acquacotta (unsafe)" to continue. Your credentials are only used by you.

# License

This project is licensed under the GPL-3.0 License.

<!-- gatehouse cross-repo verification (temporary) -->
