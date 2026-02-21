# Discord-Drive
A storage solution for discord. 

# How does Discord-Drive work?
Discord Drive is a storage solution using a exploit in discords bot system.
* How it works:
  * Decrypting file into bianary
  * Translating bianary into base64
  * Spitting the base64 into 5.15 MB chunks
  * Sending 5.15 MB base64 chunks into discord

* How Reconversion works:
  * Takes 5.15 MB base64 from discord
  * Adds them together and encrypts them back to bianary
  * Use the bianary to convert it back into your original file
  * Sends your file back onto your computer

# How to setup the requirements for the tool

# Linux:
* Directions for use:
  * Open Visual studio code
  * Navigate to the view tab
  * Click terminal

**1. Paste this into the terminal**
```bash
python -m venv venv
```

**2. Activate the environment you just created**
```bash
source venv/bin/activate
```

**3. Install requirments from the txt**
```bash
pip install -r requirements.txt
```

# Windows:
* Directions for use:
  * Install python
  * Install pip
  * Open CMD

**1. Install pip requirements**
```bash
pip install -r requirements.txt
```
# Setting up Discord Bot

Navigate to the [Discord Developer Portal](https://discord.com/developers/applications)
* Creating discord bot
  * Click new application
  * Name your bot and select the agreement box
  * Click create
 
* Setting Permissions / Copying bot token
  * Navigate to the bot section on the left hand side
  * Select the box that says "Message Content Intent"
  * Scroll up in the bot tab
  * Reset token / Copy it and save it for later

* Inviting the bot to your server
  * Scroll down to "OAuth2 URL Generator" and select bot
  * Scroll down more to Bot Permissions and select Administrator
  * Scroll down to Generated URL and copy the link
  * Paste that link into your browser and invite the bot to the server



    






