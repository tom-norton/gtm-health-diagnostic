# Connecting Claude Desktop to this project (MCP setup)

This guide adds this project's diagnostic tools directly into Claude Desktop, so you can ask Claude things like *"check the health of the Onboarding stage"* in a normal conversation, and it answers using this project's actual dataset — without opening the web dashboard at all.

No coding experience is required. You'll copy and paste a few commands into a terminal window and edit one small settings file. Budget about 15 minutes.

## What is MCP, in plain terms

MCP (Model Context Protocol) is a standard way to give Claude access to a specific set of tools — in this case, three functions that read this project's funnel data and answer specific diagnostic questions. Without it, Claude only knows what's in its training data and whatever you type. With it, Claude can look something up in this project's real dataset and answer with the actual number, on demand, inside a normal chat.

## What you'll need

- **Claude Desktop** installed (the desktop app, not the website) — download it from Anthropic's website if it isn't already installed.
- A computer running macOS or Windows.
- About 15 minutes and a willingness to copy-paste a few commands.

---

## Step 1 — Download the project

1. Go to the project's GitHub page.
2. Click the green **Code** button, then **Download ZIP**.
3. Find the downloaded ZIP file (usually in your Downloads folder) and double-click it to unzip it. Move the resulting folder somewhere you'll remember — for example, your Documents folder.

Note the exact location of this folder — the next steps need it.

## Step 2 — Install Python (if you don't already have it)

This project's tools are written in Python. Most computers don't come with a recent enough version pre-installed.

1. Go to **python.org/downloads** and click the download button for the latest version.
2. Run the installer.
   - **On Windows:** on the first installer screen, check the box that says **"Add python.exe to PATH"** before clicking Install — this step is easy to miss and important.
   - **On Mac:** run through the installer normally.
3. If Python is already installed on your machine (some Macs come with an older version), that's usually fine — this project works with any reasonably recent Python 3.

## Step 3 — Open a terminal

A terminal is a plain window where you type commands instead of clicking things.

- **On Mac:** press `Cmd + Space`, type `Terminal`, press Enter.
- **On Windows:** press the Windows key, type `PowerShell`, press Enter.

## Step 4 — Move into the project folder and install its requirements

In the terminal, type `cd ` (with a space after it), then drag the project folder from Step 1 into the terminal window — this fills in the correct path automatically — then press Enter.

Then install the required packages by copy-pasting one of these (matching your operating system) and pressing Enter:

**Mac:**
```
python3 -m pip install -r mcp_server/requirements.txt
```

**Windows:**
```
python -m pip install -r mcp_server/requirements.txt
```

This downloads a handful of small packages the project's tools depend on. It can take a minute or two.

## Step 5 — Find your Python's exact location

Claude Desktop needs the full, exact path to the Python program on your computer, not just the word "python." Get it by copy-pasting one of these into the same terminal window:

**Mac:**
```
which python3
```

**Windows:**
```
where python
```

This prints a path — something like `/usr/bin/python3` on Mac, or `C:\Users\YourName\AppData\Local\Programs\Python\Python312\python.exe` on Windows. **Copy this exact line** — it's needed in the next step. (Windows may print more than one line; use the first one.)

## Step 6 — Edit Claude Desktop's settings file

1. Open Claude Desktop.
2. Go to **Settings → Developer**, and click **Edit Config**. This opens a settings file in a text editor. (If there's no existing file, Claude Desktop will create one — that's normal for a first-time setup.)
3. The file should look like this (it may already have other content in it — if so, only add the `gtm-bowtie-diagnostic` part shown below, being careful with the commas):

```json
{
  "mcpServers": {
    "gtm-bowtie-diagnostic": {
      "command": "PASTE_YOUR_PYTHON_PATH_HERE",
      "args": ["PASTE_YOUR_PROJECT_FOLDER_HERE/mcp_server/server.py"]
    }
  }
}
```

4. Replace `PASTE_YOUR_PYTHON_PATH_HERE` with the path from Step 5 (keep the quote marks around it).
5. Replace `PASTE_YOUR_PROJECT_FOLDER_HERE` with the full path to the project folder from Step 1 (keep `/mcp_server/server.py` attached after it).
6. Save the file and close the editor.

**A tip on accuracy:** every character matters in this file — an extra or missing comma, bracket, or quote mark will stop it from working. Change only the two placeholder values above; don't add or remove any punctuation around them.

## Step 7 — Restart Claude Desktop

Fully quit Claude Desktop (not just close the window — use the app menu to Quit) and reopen it.

## Step 8 — Try it out

Start a new conversation in Claude Desktop and ask something like:

> Using the gtm-bowtie-diagnostic tools, check the health of the Onboarding stage.

If it worked, Claude's response will show it used a tool (usually a small indicator or expandable detail in the reply) and will cite specific numbers — conversion rates, days-in-stage — rather than a generic answer. Good follow-up questions: *"Has the Renewal to Expansion conversion rate always been this good, or is it new?"* or *"What's the recommended play for a leak at the Adoption stage?"*

---

## If something's not working

- **Claude doesn't seem to use any tool, or says it doesn't have access to one** — double-check the settings file from Step 6 for a typo or missing comma, and make sure Claude Desktop was **fully** quit and reopened, not just minimized.
- **A "command not found" or "python not found" type error appears** — Python isn't installed correctly, or (on Windows) the "Add to PATH" box wasn't checked during installation. Reinstall Python and make sure that box is checked.
- **The path from Step 5 doesn't look right, or the terminal shows an error instead of a path** — Python may not have installed correctly. Try closing and reopening the terminal window after installing Python, then repeat Step 5.
- **Still stuck** — the exact same three tools are also available through the project's web dashboard (no setup needed there) — that's a good fallback while sorting out the desktop connection.

## What's actually happening, if you're curious

This project defines three specific functions — check one funnel stage's health, look at one transition's history, and recommend a fix for a leak — and makes them available two ways: inside its own web dashboard, and standalone over MCP for any MCP-compatible app to use, like Claude Desktop. What was just set up is the second path: Claude Desktop now runs a small local program (`mcp_server/server.py`) that answers those same three questions, using the project's real dataset, whenever a conversation calls for it.
