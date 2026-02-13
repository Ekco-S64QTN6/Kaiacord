# 🛠️ Project 1999 Technical Troubleshooting Cheat Sheet

**Last Updated:** 1770942200.4336863
This document is a synthesized guide based on community-vetted solutions from the P99 Technical Discussion forums.

### [Missing wsock32.dll file in P99v62 download patch]
- **Symptom**: User unable to extract or find the `wsock32.dll` file after downloading and attempting to apply the P99v62 patch multiple times on different computers and operating systems (Windows 10, XP).  The user is receiving errors related to client not supported characters during login.
- **Resolution**:
    - **Initial Suggestion (Ekco):** Check for antivirus software (Avast, Norton, etc.).
    - **Suggested Solution 1 (Belambic):** Attempt to reload the missing DLL using `sfc /scannow` or replace it with a downloaded copy from `dll-files.com`.
    - **Alternative Explanation (Likx):**  Suggests the file might not be needed for EQ v62, pointing to `dsetup.dll` as potentially more relevant.
    - **Further Explanation (Lambparade):** `wsock32.dll` is a standard Windows library for network communications and is generally useful.  `dsetup.dll` is suggested as an anti-cheat component.
    - **Practical Solution (Lambparade):** Download `wsock32.dll` from `https://www.dll-files.com/download/2...BSSEZEdWF0Zz09` and extract it to either `C:\Windows\System32` (for 64-bit Windows) or `C:\Windows\SysWOW64` (for 32-bit Windows), followed by a system restart.
    - **Troubleshooting Assistance (Lambparade):** Offered direct message assistance, but new account restrictions prevented communication.



### [Antivirus Interference]
- **Symptom**: User experiencing errors ("client not supported character") despite disabling Windows Defender and attempting exclusions for the launcher and `eqgame.exe`.
- **Resolution**: No direct resolution provided beyond the initial suggestion to check for antivirus interference. The user's extensive attempts to disable and exclude antivirus software were documented.

---

### Wiki Performance Issues
- **Symptom**: The wiki is extremely slow, described as "one tick above completely unusable."
- **Resolution**: Link provided to another thread (https://www.project1999.com/forums/s...d.php?t=446264) likely containing further discussion or attempted solutions. The post "Probably moaning more will help!" is sarcastic and doesn't represent a technical solution.

---

### wsock32.dll and eqgame.dll Deletion Error
- **Symptom**: The game launcher repeatedly requests the user to delete `wsock32.dll` and `eqgame.dll` from the Everquest Titanium directory. This occurs even after various troubleshooting steps like running as administrator, setting compatibility mode, and unblocking DLLs.
- **Resolution**: Creating a desktop shortcut to the launcher file resolves the error. Directly running the launcher from its native folder does not work, suggesting a pathing or permissions issue.

### Windows Defender Interference
- **Symptom**: Windows Defender is blocking files within the Everquest Titanium installation directory, causing errors and requiring repeated unblocking.
- **Resolution**:
    - Temporarily disable Windows Defender entirely.
    - Add the Everquest Titanium installation folder, P99 download/unzip folders, and the zip file itself to Windows Defender exclusions.
    - Manually unblock the zip file after download.
    - Use PowerShell to unblock all files within the Everquest Titanium folder using the command `dir -ReCurse | Unblock-File`.

### eqgame.exe Compatibility Issue
- **Symptom**: The game fails to launch and displays errors.
- **Resolution**: Set the compatibility mode of `eqgame.exe` to Windows XP SP2.

### Launcher Pathing Issue
- **Symptom**: The launcher fails to find `eqgame.exe` initially.
- **Resolution**: Manually edit the `Launch Titanium.bat` file to include the full path to `eqgame.exe` (e.g., "F:\Everquest\eqgame.exe patchme").

---

### Wiki Transclusion Issue - Editing Magician Gear List
- **Symptom**: User attempting to edit the Magician gear list on the wiki encountered only a single line of code: `{{#lsth:Players:Velious Raiding Gear|[[Magician]]}}`. Unable to directly edit the gear list.
- **Resolution**: The gear list is transcluded from a separate page ("Players:Velious Raiding Gear"). To edit the list, the user needs to navigate to the source page, find the "Magician" section, and edit that section directly. The user needs to edit the page `https://wiki.project1999.com/index.php?title=Players:Velious_Raiding_Gear&action=edit` to modify the gear list.

---

### Character Transfer Request
- **Symptom**: User wants to transfer characters from the Blue server to the Green server.
- **Resolution**: Character transfers are not possible.

---

### Character Freezing/Slow Loading
- **Symptom**: Character freezes for 1-2 seconds, especially during spell casts, inventory opening, moving, or auto-attacking. Game loading became extremely slow. Problem occurred on multiple servers (P99 and Quarm). Previously worked fine.
- **Resolution**: The SSD containing the game installation was failing. Moving the game to a different, healthy SSD resolved the issue.



### Slow Loading
- **Symptom**: Game loading became extremely slow.
- **Resolution**: The SSD containing the game installation was failing. Moving the game to a different, healthy SSD resolved the issue.

---

### Screen Locks Up/Rendering Issues
- **Symptom**: The screen freezes on the last viewed image, minimizing and maximizing results in a black screen and rendering failure. The user remains in the game and can still perform actions, but visuals are locked. Occurs frequently, especially when transitioning between South and North Qeynos near "The Cobbler."
- **Resolution**: Using dgVoodoo2 appears to resolve the issue. A YouTube guide is suggested for easy setup.

---

### Full Screen Instability/Reversion
- **Symptom**: The game reverts out of full screen mode frequently.
- **Resolution**: Use "full screen windowed mode" as a workaround (link provided: https://wiki.project1999.com/User_In...ndowed.22_Mode).

### Mouse Look Sensitivity Issue
- **Symptom**: Vertical mouse look is excessively sensitive compared to horizontal mouse look, causing the camera to rapidly zoom to the sky or floor.
- **Resolution**: Limit the maximum frame rate to 60, either in the game's Options menu or by modifying the `eqclient.ini` file using `MaxFPS=60`.

---

### SMS Recovery Service Not Functioning
- **Symptom**: User registered a mobile number for SMS recovery but did not receive an SMS confirmation code after 20 minutes. This blocked them from proceeding with account setup.
- **Resolution**: User discovered they could proceed without completing the SMS recovery setup. The SMS recovery function itself was never successfully configured or used.

---

### Holyforge Discipline Crippling Blows on Undead Targets
- **Symptom**: Holyforge Discipline was not reliably applying crippling blows to undead targets.
- **Resolution**: The issue was fixed and will be included in the next patch. (Link to related thread: https://www.project1999.com/forums/s...d.php?t=278044)

---

### Borderless Gaming Program Usage
- **Symptom**: User unsure if "Borderless Gaming" program is allowed on Project 1999, concerned it might be considered a 3rd party program.
- **Resolution**: The program is considered perfectly fine and widely used as it doesn't interact with the game.

---

### Email Verification Failure
- **Symptom**: User (son of poster) unable to log in due to not receiving email verification.
- **Resolution**: User was able to request a new verification email via the link: https://www.project1999.com/forums/r...o=requestemail

---

### [Installation Script Error - "The syntax of this command is not correct"]
- **Symptom**: User received an error message "The syntax of this command is not correct" when attempting to run the `install.bat` script.
- **Resolution**: Suggestion to use the manual installation method.

### [Blade Texture Inclusion Clarification]
- **Symptom**: User inquired about whether blade textures were included and what the differences were.
- **Resolution**: Some blade textures are included, but there is a separate set available. Cucumbers was mentioned as the person who could provide more details.

### [Windows "Run anyway" prompt during installation]
- **Symptom**: Windows security prompts users to "Run anyway" when executing `install.bat` and `uninstall.bat`.
- **Resolution**: User needs to manually select "Run anyway" to proceed with the installation/uninstallation. (This is more of a workaround than a direct fix, but it's a noted issue.)

---

### Cannot Log In - Incorrect Credentials/Account Issues
- **Symptom**: User unable to log in with username/password. Believes account may have been deleted.
- **Resolution**: User may be using forum credentials instead of the in-game account credentials. Suggestion to check login server accounts via the top left box on the front page, differentiating between accounts created on Project 1999 vs. EQEmu.

### Potential Patch Requirement
- **Symptom**: User experiencing login issues.
- **Resolution**: User may need to apply the latest patch.  In-game messages should direct the user to apply the patch if necessary.

---

### EQ MIDI Music Sounds Terrible by Default
- **Symptom**: The default MIDI music in EverQuest sounds "terrible" or "not right" compared to how it was originally intended to sound with an AWE32 Sound Blaster card. Some soundfonts can sound even worse than the default.
- **Resolution**: Replace the default MIDI soundfont with "1mgm.sf2" (AWE32 Rom Dump Soundfont) and use the BASSMIDI driver. This involves downloading the soundfont, installing the BASSMIDI driver, adding the soundfont to the driver configuration, and selecting BASSMIDI as the default MIDI synth.



### Glitchy Sound during Music Playback
- **Symptom**: Some users reported a glitchy sound during music playback.
- **Resolution**: The glitchiness was attributed to the user's screen recording software (Fraps) running concurrently and was not inherent to the soundfont or driver configuration.

---

### [Login Server Connectivity Issues - Hanging Screen, Empty Server List, Login Failures]
- **Symptom**: Hanging screen of nothingness after entering credentials, zero servers listed on server select screen, populated server list with failures after clicking Login. Intermittent success.
- **Resolution**: Disconnecting from a company VPN resolved the issue for one user.  Changing DNS to Google's 8.8.8.8 improved connection stability.  A possible correlation was noted between streaming background music and increased lag/disconnections. Disconnecting non-essential devices from the home network may alleviate the problem. Replacing ISP-provided network equipment (modem, router) is suggested as a long-term solution.

### [Zone Disconnects]
- **Symptom**: Disconnecting every time zoning.
- **Resolution**: Changing DNS to Google's 8.8.8.8 improved stability.

### [General Network Instability/Lag]
- **Symptom**: Sawtooth wave pattern observed in network monitor.
- **Resolution**: Streaming background music seemed to correlate with increased lag (though this was later jinxed).

### [Blank Screen/Empty Server List/Login Errors]
- **Symptom**: Blank screen, empty server list, or login errors after selecting a server.
- **Resolution**: Refer to the Project 1999 Wiki article on Tech Screen Problems (link provided).

### [ISP Related Issues]
- **Symptom**: General connectivity problems.
- **Resolution**: No direct resolution, but potential for issues related to ISP's equipment and network congestion.

---

### IP Exemption Request
- **Symptom**: User wants to play with their girlfriend but is likely being blocked by the server's anti-cheating measures.
- **Resolution**: User needs to submit a request through the petition forums, following the instructions and providing the required information outlined in an announcement.

---

### Forum Account Password Recovery - No Email Access
- **Symptom**: User locked out of Forum Account and does not remember or have access to the email address associated with the account.
- **Resolution**: There is currently no way to proceed.

### Forum Account Password Recovery - No SMS Access
- **Symptom**: User can access the Forum Account, but no longer has access to the SMS number attached to it.
- **Resolution**: There is currently no way to proceed.

### Loginserver Account Password Recovery - General Process
- **Symptom**: User has lost access to Loginserver Account passwords.
- **Resolution**: Requires first regaining access to the associated Forum Account. Then, if the current password is known, change it. If not, reset all Loginserver Account passwords via the SMS system (requiring SMS verification and email verification).

### Loginserver Account Password Reset - SMS Verification Issue
- **Symptom**: SMS verification code not being accepted.
- **Resolution**: Ensure the SMS verification code is verified. If no access to the associated email, the SMS number will become active after 7 days.

---

### Accidental Character Deletion
- **Symptom**: User accidentally deleted a level 28 bard character, believing they were exiting the game.
- **Resolution**: User advised to submit a petition through the designated forum section (link provided) for potential character restoration. Restoration may take a significant amount of time (potentially months) due to a backlog.

---

### Wiki Account Creation and Editing Permissions
- **Symptom**: Users are unable to edit the wiki and are prevented from creating new user accounts. The error messages indicate needing "Users" group permission to edit and "Administrators" group permission to create accounts.
- **Resolution**: User account creation was temporarily disabled due to bot spamming. The intended workflow (self-account creation followed by editing) is broken. A permanent fix (e.g., CAPTCHA) was planned but not implemented. Users are advised to contact Rogean for feedback and potential resolution. Admin-mediated account creation is the current workaround, but this is not the usual operation of the wiki.



### Wiki Spam Prevention - Account Creation Disabled
- **Symptom**: Users cannot create new accounts.
- **Resolution**: Account creation was disabled to prevent wiki spamming. No estimated time of arrival (ETA) for re-enabling it was provided.

---

### Game Freezes at Specific Locations
- **Symptom**: The game randomly freezes, but the game itself continues to run (footsteps can be heard). Freezing often occurs while running, turning around, or in specific locations (Neriak zoning, Overthrre Outpost, Felwithe).  The issue appears to be screen-related, not a full game crash.
- **Resolution**:  User `Mortdecai99` suggests trying the "DG VooDoo Fix" (link provided: https://www.project1999.com/forums/s...1&postcount=14). User `RPGrandPa` was also directed to the "Tech_Support#Game_Freezing_or_Crashing_At_Specific _Places_In-Game" thread.

---

### F-Key Conflicts with Windows/Computer Options
- **Symptom**: Pressing F-keys in-game triggers a computer options window and shrinks the game window.
- **Resolution**: Remap F-keys in the EQ in-game options (ALT-O) to different key combinations. This suggests a conflict between EQ's F-key bindings and a keyboard setting within Windows.

---

### [Character Bank Transfer Issues]
- **Symptom**: Difficulty transferring gear between characters due to a lack of shared bank slots and issues with the character selection process (kick-offs, timers, etc.).
- **Resolution**: User requests the addition of shared bank slots, potentially from a reference to "ykesha". This would alleviate the need for manual gear transfers.

### [Luclin Content Integration Concerns]
- **Symptom**: Adding Luclin content without addressing the power creep would lead to trivialization of endgame content. Players are already soloing high-level encounters.
- **Resolution**:  No explicit resolution, but a consensus that adding Luclin content without significant balancing adjustments would be detrimental to the game's challenge.

### [Lack of Development Interest]
- **Symptom**: The Project 1999 team appears disinterested in custom content development.
- **Resolution**: No resolution, merely an observation of the current state of affairs.

### [THJ Server Status]
- **Symptom**:  The THJ server (likely a private EverQuest server) is permanently shut down.
- **Resolution**: No resolution, simply an announcement of the server's closure.

### [Server Status - Green/Blue Servers]
- **Symptom**: Green and Blue servers are no longer active.
- **Resolution**: No resolution.

---

### Missing Color Behind Spellgems/Debuffs/Buffs
- **Symptom**: Spellgems in the spellbook and buff bar lack the colored background (red for debuffs, blue for buffs). This is because the `CS_buttons.bmp` file was made transparent to resolve a conflict with the buff bar.
- **Resolution**: The author made the `CS_buttons.bmp` file transparent as a temporary workaround. A proper solution requires further investigation and modification of the UI files.

### Inability to Increase Group/Player Window HP Bars
- **Symptom**: The author was unable to increase the size of the health bars in the group and player windows. The `EQUI_PlayerWindow.xml` and `EQUI_GroupWindow.xml` files are too complex for their current skill level.
- **Resolution**: No resolution provided. The author expressed intent to address this in the future, potentially incorporating elements from Rustle UI.

### Unfinished Buff Bar (Beyond 10 Buffs)
- **Symptom**: The buff bar is incomplete beyond the first 10 buffs. The author hasn't been able to test or display more than 10 buffs at once.
- **Resolution**: The author offered to fix this with assistance from players using buff bots in the Tunnel zone.

### Missing/Unscaled High-Level UI Elements
- **Symptom**: UI elements that become active at higher levels are either missing or not scaled correctly due to the author's lack of high-level characters to test with.
- **Resolution**: No resolution provided. Requires testing with higher-level characters.

### Inventory Window Issues
- **Symptom**: Initial release had issues with the inventory window.
- **Resolution**: Cleaned up the inventory window in a subsequent update.

### Item Name Size Issue
- **Symptom**: Item names were not displaying correctly in item boxes.
- **Resolution**: Fixed the item name size in an update.

### Player Health/Mana Bar Replication
- **Symptom**: Request for a player health and mana bar similar to the target bar (inspired by Rustle UI).
- **Resolution**: The author planned to implement this in the future, contingent on resolving the group/character window issues.

### Group Window Issues
- **Symptom**: The group window was "dirty" - missing details, and f2-f6 icons were misaligned.
-

---

### Python Version Compatibility Issue
- **Symptom**: User running eqalert on Gentoo with Python 3.10.7 receives errors: "not enough arguments for format string", "Expecting value", "'NoneType' object has no attribute 'settings'". Config file is overwritten and emptied upon execution.
- **Resolution**: The developer is using Python 3.7.3 locally. An issue will be added to the repository to investigate the package version reporting and narrow the tested Python version range in setup.py. The user is advised to check paths in the settings.json file. A gist with example config files is provided.



### Spell Parsing Incompleteness (Resolved)
- **Symptom**: Initially, the parser did not match all spell text.
- **Resolution**: Version 3.2.5 included all spell text matching.

---

### FPS Cap with AMD GPU
- **Symptom**: User experiencing a persistent FPS cap of 48 FPS on a new PC with an AMD CPU and AMD GPU, despite attempts to limit FPS using Radeon Chill and AMD Control Panel settings. The issue persists across different launch methods (standalone, batchfile, wineq2, dgvoodoo2). ALT+O settings show FPS capped at 39-40 with a 60 FPS limit, and 47-48 with a 100 FPS limit.
- **Resolution**: Adding `vsync=1` to the `eqclient.ini` file resolves the FPS cap. The post asks for clarification on the appropriate category within the ini file (General or Video).

---

### Unable to join the server after a lockup/death
- **Symptom**: Receiving "an unknown error occurred while trying to join the server" after a lockup, particularly after a death in Paineel.  Users are unable to join the green server after successful login.
- **Resolution**: The issue resolved itself after approximately 90 minutes. It appears to be a temporary server-side issue. User was offered a resurrection by another player.

---

### [Performance Issues (Rapid/Slow Movement, Crashing, Frame Rate Problems)]
- **Symptom**: Rapid movement, very slow movement/frame rate, crashing, double durations, intermittent graphics lag, stalling in zones with complexity or many players.
- **Resolution**: Running EverQuest under WinEQ2 resolves these issues. Download WinEQ2 from lavishsoft.com. Requires registration (free) to run.

### [Login Requirement for WinEQ2]
- **Symptom**: User is prompted to log in to download or run WinEQ2. Difficulty avoiding the login requirement.
- **Resolution**:  Registration is free and doesn't require personal information. A temporary login (username: Activate, password: wineq2) was provided, but its functionality for multiple users is uncertain.  The process involves navigating through a website and clicking specific tabs. There's a paid version and a free version; users might be getting stuck with the paid/subscription version.

### [Removing the Top Window Bar]
- **Symptom**: User wants to get rid of the top window bar in WinEQ2.
- **Resolution**: Use the Borderless-Gaming script from GitHub: https://github.com/Codeusa/Borderless-Gaming

---

### EQEmulator Account Linking Failure
- **Symptom**: User is unable to link their Project 1999 and EQEmulator accounts. Receiving a PDOException error: "SQLSTATE[HY000] [1045] Access denied for user 'p99link'@'localhost' (using password: YES)"
- **Resolution**: The error indicates a MySQL access denied issue for the 'p99link' user. This suggests incorrect credentials or insufficient permissions for the user 'p99link' when attempting to access the MySQL database from the EQEmulator server.  Further investigation into the MySQL user configuration and password is required to resolve.

---

### DirectX 9 Implementation Bug on Windows 11 ARM
- **Symptom**: Characters modules did not appear when running P99 on Windows 11 ARM within UTM.
- **Resolution**: Copying `D3D8.dll`, `D3DImm.dll`, and `DDraw.dll` files from the MS\x86 folder, along with the executable itself, into the P99 directory, and using a batch file to launch the game (`C:\Windows\System32\cmd.exe /C Start /affinity 1 .\eqgame.exe patchme`) resolved the issue.

### Mouse Speed and Input Issues on Windows 11 ARM (UTM)
- **Symptom**: Slow pointer speed and general input issues when running P99 on Windows 11 ARM within UTM.
- **Resolution**: Switching to Parallels resulted in smoother performance and proper mouse/keyboard functionality.

### Mouse Speed Issues on Parallels
- **Symptom**: Mouse speed issues when running P99 on Parallels.
- **Resolution**:  Adding the boot flag `devices.usb.enable_mouse=0` in the boot order advanced settings helped in Parallels 16. This didn't work in Parallels 17.

### Memory Read Errors When Launching .bat File in Parallels
- **Symptom**: Memory read errors when launching the .bat file within Parallels.
- **Resolution**: Turning off compatibility mode, enabling "Safe Emulation", and avoiding running as administrator.

### Crashes with Error in VMware Fusion on M4 Max
- **Symptom**: Crashes after reaching the server selection screen when attempting to run P99 in VMware Fusion on an M4 Max.
- **Resolution**: Enabling "Safe Emulation" appeared to resolve the issue.

---

### Crystal Chitin Shield Light Emission Issue
- **Symptom**: The Crystal Chitin Shield stopped emitting light externally. This occurred sometime within the past week. The user initially suspected issues with titanium or a bug with the item or character.
- **Resolution**: The shield was not emitting light because it was being overshadowed by the light from a Dark Ember weapon. The user initially misattributed the light to the shield. The user also learned about a list of light sources in the EQ client and how to adjust dynamic light settings.

### Lodizal Shell Shield Brightness
- **Symptom**: The Lodizal Shell Shield appeared dimmer than expected.
- **Resolution**: The shield's brightness setting in the EQ client was found to be at a low value (15). This was confirmed to be functional, indicating the client's light source list was working.

### Dynamic Light Settings and EQClient.ini
- **Symptom**: User was unaware of a list of light sources within the EQ client and how to adjust dynamic light settings in eqclient.ini.
- **Resolution**: mcoy provided a link to the Project 1999 wiki page detailing light sources: https://wiki.project1999.com/Light_source.  The user then understood the reference to checking dynamic light settings at the bottom of the light source list.

---

### No Music Playing
- **Symptom**: Sound effects are working, but no background music is playing.
- **Resolution**: Ensure `CombatMusic=1` and `Music=1` are present in the `eqclient.ini` file.

---

### Spell Icons are Jumbled
- **Symptom**: Spell icons are incorrectly assigned; SoW shows the thorns icon, Skin like Wood shows the haste icon.
- **Resolution**: Switching to a different UI (specifically QQUI) resolved the issue. Restoring from a /uifiles backup is also suggested as a potential solution.

---

### Account Banned Unexpectedly
- **Symptom**: User account "Martinals" with characters "Stringpling" and "Meatspinner" was banned without apparent reason. User receives a ban message upon login but cannot find a way to contact customer support.
- **Resolution**: User advised to create a thread in the designated support forum (https://www.project1999.com/forums/forumdisplay.php?f=25) as staff will not respond to technical issues in public forums.

---

### Grobb Town Wiki Unloading
- **Symptom**: The town wiki page for Grobb is not loading.
- **Resolution**: It is suspected to be a bug and hopefully will self-resolve within a day.

---

### Characters Disappearing After Update
- **Symptom**: User logs in but finds all their characters missing.
- **Resolution**:
    - A) Patching issues, potentially requiring file name casing adjustments based on the operating system.
    - B) User may be logged into the wrong server or account.

---

### Account Name and Password Retrieval/Reset
- **Symptom**: User forgot their login account name and password and cannot access it via clicking their forum account name (resulting in a "file not found" error). The standard "forgot password" functionality was not explicitly tested, but the user assumed it might work.
- **Resolution**: User was directed to the Project 1999 homepage, specifically the "Account System" section under "LoginServer Accounts," where they can view their login name and reset their password.

---

### [Linux Audio Issues]
- **Symptom**: Users were experiencing sound issues while using Linux.
- **Resolution**: The wiki page (https://wiki.project1999.com/Tech_Support) contained a section specifically addressing Linux audio problems, which proved helpful to multiple users.

### [General Technical Issues]
- **Symptom**: Users were experiencing various technical issues.
- **Resolution**: A comprehensive wiki page (https://wiki.project1999.com/Tech_Support) was created containing detailed solutions to a wide range of technical problems, offering an alternative to waiting for forum replies. The page contains over 5000 words.

---

### [Wiki Page Unavailability (Sebilis, Velketor's Labyrinth)]
- **Symptom**: Wiki pages for Sebilis and Velketor's Labyrinth were initially unavailable. Links from mobs within the zones were redirecting to "/Old_Sebilis".
- **Resolution**: Initially attributed to administrative work or a CloudFlare outage. The redirect issue was resolved by changing the link from "/Old_Sebilis" to "Sebilis".  The underlying cause of the redirect issue appeared to be a caching problem on the user's browser, or a temporary backend service issue. Refreshing the page was suggested as a fix.

### [Browser Cache Issues / Backend Service Problems]
- **Symptom**: User experiences intermittent issues where pages appear to be down or redirect incorrectly.
- **Resolution**: Initially suggested as a browser caching issue, resolved by refreshing the page. Later clarified as potentially a backend service problem beyond the user's control. Refreshing the page may or may not resolve the issue depending on the underlying problem.

---

### [dsetup.dll False-Positive Virus Flagging]
- **Symptom**: The `dsetup.dll` file is being flagged as a potential threat by antivirus software (specifically McAfee, Norton, and potentially AVG). This is a "Generic11" classification, indicating the software doesn't recognize the file's purpose and is issuing a warning out of caution.  Users are experiencing security warnings when attempting to use the file.
- **Resolution**:
    * **Understanding the Root Cause:** The flagging likely stems from someone submitting the file to a virus database (possibly maliciously), which resulted in a generic "unknown" classification.  Antivirus vendors often share these lists, so a single entry can be widely distributed.
    * **File Behavior:** The file itself does *not* modify files, read files, destroy the registry, or grant access to the user's computer. Its purpose is to detect cheats (Macroquest, ShowEQ) to maintain a hack-free server.
    * **Alternative Antivirus:**  Switching to a more reputable antivirus program, such as Kaspersky, can avoid the false positive.
    * **Trusting the Source:** Users can choose to trust the Project 1999 team, who have provided the game for five years without incident, despite the warning.



### [Antivirus Scanner Quality]
- **Symptom**: Some antivirus vendors (McAfee, Norton) are considered to have poor virus protection and are labeled as a scam.  AVG, while generally good, may lack the resources to quickly address false positives.
- **Resolution**: Use a better antivirus scanner such as Kaspersky.

---

### Freezing/Black Screen on Login
- **Symptom**: User experiences crashes and inability to load the game after character selection, resulting in a black screen, looping music, and inability to proceed. This occurs across multiple PCs and seemingly after recent Windows updates.  The issue sometimes manifests as a glitchy/lagging music sound upon server selection. A user reports being unable to access Task Manager during the freeze. Another user experiences issues loading into the world after server and character selection.
- **Resolution**:
    - Running the client as administrator (suggested by loramin).
    - Checking the Project 1999 wiki page regarding screen problems (https://wiki.project1999.com/Tech%20Problems/Black_Screen_Problems).
    - Rolling back recent Windows updates (suggested by Gecro).
    - Reinstalling the game and Windows (attempted by Fingurs, unsuccessful).
    - Disabling Killer Network suite (attempted by Fingurs, reporting back on results).
    - Repeatedly closing and relaunching the client and rebooting the PC (temporary workaround).

---

### Error 1017 - Persistent Login Issue
- **Symptom**: User consistently receives Error 1017 upon login across multiple accounts, laptops, and connection types (including mobile hotspot). The issue began after a relocation.  Troubleshooting steps attempted include fresh Titanium install, verifying patch files, adjusting clock speed, using "patchme", modifying eqclient.ini, and trying WinEQ2.
- **Resolution**: The user was experimenting with clock speed, which may have triggered a safeguard implemented by the server.  Refer to the Project 1999 wiki page for Technical Support - Client Update Patch (link provided).



### Clock Speed Manipulation and Error 1017
- **Symptom**: Adjusting clock speed (even within a seemingly safe range) resulted in Error 1017. This was linked to a previous incident where clock speed manipulation allowed for unintended speed advantages.
- **Resolution**: Avoid adjusting clock speed. Safeguards are in place to prevent manipulation of clock speed and may trigger errors. Refer to the Project 1999 wiki page for Technical Support - Client Update Patch.

---

### Problems with Running Project 1999 on Newer Computers
- **Symptom**: Difficulty running Project 1999 on newer computers.
- **Resolution**: Use WinEQ2. This program is free and addresses compatibility issues. (Link: http://www.project1999.com/forums/sh...d.php?t=139727)

### Playing Project 1999 on macOS
- **Symptom**: Desire to play Project 1999 on a Mac.
- **Resolution**: Follow the guide linked in the thread. (Link: http://www.project1999.com/forums/sh...ad.php?t=56238)

### Running Project 1999 Under Linux
- **Symptom**: Running Project 1999 under Linux.
- **Resolution**: Utilize Ruien's guide or the EQ Under WINE guide. (Links: http://www.project1999.com/forums/sh...d.php?t=126081, http://www.project1999.com/forums/sh...ad.php?t=21734)

### Annoying Sounds (Bag opening/closing, weather, etc.)
- **Symptom**: Loud or annoying sounds (bag opening/closing, weather, etc.)
- **Resolution**: Refer to the linked thread for solutions. (Link: https://www.project1999.com/forums/s...d.php?t=165237)

### Crashing While Zoning
- **Symptom**: Crashing while zoning.
- **Resolution**: Consult Rogean's Crashing While Zoning thread. (Link: http://www.project1999.com/forums/showthread.php?t=3604)

### Multi, Dual, and Quad-Core Issues
- **Symptom**: Issues related to multi, dual, or quad-core processors.
- **Resolution**: Refer to the linked thread. (Link: http://www.project1999.com/forums/showthread.php?t=3609)

---

### [Forgotten Username/Login Credentials]
- **Symptom**: User forgot their username for an old Project 1999 account, but remembers the password and character name ("Lizardy", Iksar Necromancer, likely on green or blue server).
- **Resolution**: Suggested solutions include:
    - Checking "Loginserver Accounts" if the account was created under the user's current forum name.
    - Checking the "Loginserver Account" links on the Project 1999 or EQEmu websites if the user has access to the forum account used to create the old account.
    - Requesting assistance in the "Petition" forum.

---

### Persistent Error 1018 and Disconnects
- **Symptom**: Frequent disconnects (DC) resulting in persistent Error 1018 messages lasting for extended periods (40+ minutes). Character corpse timer remains active upon reconnection, requiring petitioning.
- **Resolution**: The problem was likely caused by an orphaned `eqgame.exe` process. The suggested solution is to terminate the `eqgame.exe` process via Task Manager or to reboot the system (rather than shutting down).

---

### nParse Timer Reset with Multiple Mobs of the Same Name
- **Symptom**: nParse timers reset on the latest cast when fighting multiple mobs with the same name. The user wants timers to reset for each unique mob, even if they share a name.
- **Resolution**: The root cause is that nParse (and the game logs) don't differentiate between mobs, only their names. Filtering by time difference between hits is suggested as a potential workaround, but its effectiveness is limited by the frequency of hits from multiple mobs sharing the same name. It's likely impossible to reliably differentiate them based on timestamps alone.

---

### Account Ban - Unclear Cause
- **Symptom**: Users are reporting being banned from the game without prior warning, email notification, or clear explanation. They claim to be following server guidelines.
- **Resolution**: Users are directed to the "Petition Forums" (link provided) to inquire about their bans, as discussing suspensions/bans publicly is discouraged. This implies a process exists for users to appeal or understand their bans, but the root cause of the bans isn't addressed in this thread.

---

### Password Reset Issues After Reinstallation
- **Symptom**: User unable to log in after reinstalling the game and moving to a new hard drive; existing passwords no longer work.
- **Resolution**: Provided a link to a password recovery form (https://drive.google.com/file/d/1f19...ew?usp=sharing and https://drive.google.com/file/d/1TVB...ew?usp=sharing).  Implies the issue is related to an "EqEmu" account.

---

### [Named Mob Spawns Failing to Appear]
- **Symptom**: Players are reporting a lack of named mob spawns (specifically Quill) during foraging cycles. The spawns appear to be intermittent and random, with periods of no spawns followed by sudden appearances.
- **Resolution**: No clear resolution provided. The prevailing belief seems to be that it's a random occurrence ("a streak") and often resolves itself spontaneously.

---

### Unexpected Ban
- **Symptom**: User reports being banned from the game without apparent reason.
- **Resolution**: User advised to post their query in the Petition forums for review (link provided).

---

