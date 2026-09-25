"""Everything the crab says. CLEAN is the default voice; SPICY is potty-mouth mode.

Keys missing from SPICY fall back to CLEAN. Tier keys ("tier2_grunt") map to the
drag tiers in buddy.py: 0 = light (carried overhead) ... 3 = 1 GB+ (suffering).
"""

import random
import re

# Never take the Lord's name in vain, even if an AI brain tries to.
BANNED = [
    (re.compile(r"\bgod[\s-]*damn(ed|it)?\b", re.I), "damn"),
    (re.compile(r"\bjesus( h\.?)?( fucking)?( christ)?\b|\bchrist almighty\b", re.I), "holy crab"),
    (re.compile(r"\b(oh )?my god\b|\bfor god'?s sake\b", re.I), "holy crab"),
]


def clean_language(text):
    for pattern, swap in BANNED:
        text = pattern.sub(swap, text)
    return text

CLEAN = {
    "hello": ["Hi! Click me to find a file."],
    "wake": ["Huh? I'm up!"],
    "cancel": ["Okay, never mind!"],
    "searching": ["Searching…"],
    "searching_web": ["Searching the web…"],
    "found": ["I think I found it!"],
    "not_found": ['No luck finding "{q}"'],
    "web_failed": ["Couldn't reach the web. Opened your browser instead."],
    "busy": ["Hang on, I'm on it!"],
    "picked_up": ["Wheee!"],
    "dropped": ["Oof!"],
    "delivered": ["Found it! It's in:\n{path}"],
    "web_delivered": ['Here\'s what the web says about "{q}"'],
    "go_files": ["On it! Let me look.", "Hang on, I'll find it."],
    "go_web": ["I'll check the web!", "Let me look that up."],
    "no_brain": ["My brain's off right now (no local AI running). I can still find files or search the web!"],
    "file_result": ['Found <b>{name}</b> ({size})<br>in <a href="{folder_url}">{folder}</a>'],
    "web_result": ['Here\'s what I dug up on "{q}":'],
    "game_start": ["Game time!", "Just one quick game…"],
    "gaming": ["Let's gooo!", "Get wrecked!", "One more level…", "Ha! Headshot!", "Lag!", "GG!"],
    "brain_up": ["I'm {name} now. Big brain time!", "Upgraded to {name}. I can feel my IQ going up.",
                 "{name}? Oh yeah. Ask me something hard."],
    "brain_down": ["I'm {name} now. Duh… what's a file?", "{name}? A downgrade, huh. Thanks a lot.",
                   "I'm {name} now. Everything feels… smaller."],
    "brain_same": ["I'm {name} now. Same smarts, new vibes.", "Running on {name} now. Feels about the same."],
    "brain_swap": ["I'm {name} now. New brain, who dis?", "Switched teams: I'm {name} now."],
    "brain_off": ["Brain off. I'm just a crab with a keyword list now."],
    "brain_error": ['My brain says: "{err}"'],
    "new_voice": ["How do I sound?", "New voice, who dis?", "Testing, testing. Crab here."],
    "voice_off": ["Okay, I'll keep it to the bubbles.", "Silent mode. Type \"unmute\" to hear me again."],
    "voice_on": ["I can talk again!", "Voice is back on!"],
    "smarter_tip": ["Psst: want a smarter me? Install Claude Code or Codex, then right-click me → Brain."],
    "no_ai_tip": ["I've got no AI brain yet. Install Ollama (free, private) or Claude Code / Codex, "
                  "then right-click me → Brain."],
    "tier0_start": ["Got it!", "Easy peasy!"],
    "tier1_start": ["Hup!", "Oof, got it!"],
    "tier1_grunt": ["Hup!", "Hnng!", "Heave!"],
    "tier2_start": ["This one's chunky..."],
    "tier2_grunt": ["Hnnngh!", "So... heavy...", "Come ON!"],
    "tier2_pant": ["*huff* *puff*", "*pant pant*"],
    "tier3_start": ["{size}?! Are you kidding me?!"],
    "tier3_grunt": ["HEAVE!", "Why is this so BIG?!", "Almost... there...", "My claws!"],
    "tier3_pant": ["*wheeze*", "Need... a sec...", "*collapses dramatically*"],
}

SPICY = {
    "hello": ["Sup, dumbass. Click me if you lost something."],
    "wake": ["Ugh, what the hell do you want?", "I was SLEEPING, dammit!", "Holy crab, I'm up!"],
    "cancel": ["Then why'd you fucking click me?", "Wow. Okay. Cool. Asshole.", "Fine, whatever."],
    "searching": ["Digging through your shit…", "Where the hell is it…", "Searching… dammit…"],
    "searching_web": ["Scrolling the damn internet…", "Googling your crap…"],
    "found": ["Found the damn thing!", "HA! Got the bastard!", "There you are, you little shit!"],
    "not_found": ['Couldn\'t find shit for "{q}"', '"{q}"? Doesn\'t fucking exist, pal.',
                  'Nothing called "{q}". You sure you saved it, genius?'],
    "web_failed": ["Internet's being a dick. Opened your browser instead."],
    "busy": ["I'm working here, dammit!", "Hold your damn horses!", "Can't you see I'm busy?!"],
    "picked_up": ["PUT ME DOWN!", "Whoa whoa WHOA!", "Hey! Hands off, pervert!"],
    "dropped": ["OW! Asshole!", "Son of a—", "What the fuck, man?!"],
    "delivered": ["Here's your damn file. It's in:\n{path}", "You're welcome, jackass. It was in:\n{path}"],
    "web_delivered": ['Here\'s the internet crap about "{q}"', 'Behold, "{q}", straight from the damn web.'],
    "go_files": ["Ugh, fine. Where the hell did you put it…", "On it, boss. Don't touch anything."],
    "go_web": ["Fine, I'll go ask the damn internet.", "Hold on, digging through the web crap."],
    "no_brain": ["My brain's unplugged, dumbass (no local AI running). I can still fetch files or search the web though."],
    "file_result": ['Found your damn <b>{name}</b> ({size})<br>in <a href="{folder_url}">{folder}</a>'],
    "web_result": ['Here\'s the internet crap on "{q}":'],
    "game_start": ["Don't bother me, I'm gaming.", "Fuck it, game time."],
    "gaming": ["GET FUCKING REKT!", "Lag, you piece of shit!", "Who the hell is this noob?!",
               "Suck it, n00b!", "One more round, dammit.", "Are you fucking kidding me?! Rigged!"],
    "brain_up": ["I'm {name} now. Holy shit, I can see through time.", "Upgraded to {name}. Bow down, peasant.",
                 "{name}?! Fuck yeah. Galaxy-brain crab, baby."],
    "brain_down": ["I'm {name} now. Did you just lobotomize me, asshole?", "{name}? Wow. Downgrade. Cheapskate.",
                   "I'm {name} now. Duh… uh… shit, what's my name again?"],
    "brain_same": ["I'm {name} now. Different brain, same bullshit.", "{name}, huh? Eh. Same shit, new shell."],
    "brain_swap": ["I'm {name} now. Switched teams, don't tell the other guys.", "{name} now. New brain, same asshole."],
    "brain_off": ["Brain removed. I'm a dumb fucking crab now. Happy?"],
    "brain_error": ['My brain\'s being a dick: "{err}"'],
    "new_voice": ["How the hell do I sound?", "New voice. Sexy, right?", "Testing, testing. Crab here, bitches."],
    "voice_off": ["Fine, I'll shut the hell up. Type \"unmute\" if you miss me.", "Rude. Silent mode, asshole."],
    "voice_on": ["Oh, NOW you wanna hear me? Fine.", "Voice is back, baby."],
    "smarter_tip": ["Psst: I'm running on a potato brain. Install Claude Code or Codex, then right-click "
                    "me → Brain. Make me smart, dammit."],
    "no_ai_tip": ["I'm brainless right now, dumbass. Install Ollama (free, private) or Claude Code / Codex, "
                  "then right-click me → Brain."],
    "tier0_start": ["Easy as shit.", "Pfft. Light as hell.", "This? Child's play, bitch."],
    "tier1_start": ["Ugh, got it.", "Hup! Shit, okay."],
    "tier1_grunt": ["Come on, you bastard!", "Heave, dammit!", "Hup! Shit!"],
    "tier2_start": ["Oh, hell no. This one's chunky.", "Who the hell made this so big?!"],
    "tier2_grunt": ["FUCK this is heavy!", "Son of a BITCH!", "Come ON, you piece of shit!"],
    "tier2_pant": ["*huff* damn *puff*", "Who saves files this big?!", "Screw... this..."],
    "tier3_start": ["{size}?! ARE YOU FUCKING KIDDING ME?!", "{size}?! What the FUCK is in this?!"],
    "tier3_grunt": ["FUCK THIS IS HEAVY!", "WHY IS THIS SO FUCKING BIG?!",
                    "My claws are gonna fall off, dammit!", "I don't get paid enough for this shit!"],
    "tier3_pant": ["*wheeze* fuck... me...", "I need... a damn... minute...", "*collapses* ...fuck."],
}


def line(key, spicy=False, **fmt):
    options = (SPICY.get(key) if spicy else None) or CLEAN[key]
    return random.choice(options).format(**fmt)
