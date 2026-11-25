import ast, datetime, fnmatch, hashlib, json, random, re

SEVERITY_RANK = {"HIGH": 0, "MEDIUM": 1, "NIT": 2}
SEVERITY_ICON = {"HIGH": "🔴", "MEDIUM": "🟡", "NIT": "🔵"}

DEFAULT_EXCLUDE_PATHS = [
    "docs/*",
    "*.md",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "go.sum",
    "Cargo.lock",
    "poetry.lock",
    "Pipfile.lock",
    "Gemfile.lock",
]

# Above this many diff lines, Gemini 3.x models get thinkingLevel "high" —
# flash-tier models miss real issues at "medium" on multi-thousand-line reviews.
THINKING_HIGH_DIFF_LINES = 1500

# Thinking models routinely exceed the 120s that sufficed for gemini-2.5;
# high thinking on a large diff needs several minutes.
GEMINI_TIMEOUT_SECONDS = 300

CLEAN_GIFS = [
    # Uncut Gems
    "https://media1.tenor.com/m/yuaLtvK1EzkAAAAd/adam-sandler-holy-shit.gif",
    "https://media1.tenor.com/m/JLMnQlvI7IgAAAAd/uncut-gems-adam-sandler.gif",
    "https://media1.tenor.com/m/qQSj3f9yA5EAAAAd/uncut-gems-adam-sandler.gif",
    "https://media1.tenor.com/m/OujKPDpopHAAAAAd/uncut-gems-disagree.gif",
    "https://media1.tenor.com/m/mNNB_l4YZXUAAAAd/adam-sandler-uncut-gems.gif",
    "https://media1.tenor.com/m/nz3H_V9w618AAAAd/uncut-gems-sports-betting.gif",
    "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExOHpueHdkZnU0aWQ0NnIyend6OGY1NXlrazk4NGZqNGxkNjF6dm5iNyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/MbMKD1zec72gaKHRmL/giphy.gif",
    "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExeHMzZjZ1a2txbGsxZzBpbnJlZDljZjB5YzMzeXZ3b3RyZGNtemJkeSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/d6R2ix5rqMzPmDugAn/giphy.gif",
    "https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExYnI3YmllYzkyZ3diZm9rNms2ODBvd2l2aGw3YzVxMjRsMm04aWh1ZyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/Xbn4I3lPUqLP5ZepV1/giphy.gif",
    "https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExZHZoNWZpc2QxOXQ3bDZrdTVnYzl4cHM4cWpmYmtqaW14d2JqZTV1MCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/Q7XhC0fWHaoA413kHG/giphy.gif",
    "https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExczlsNG5yczR4em9zajV5anV0aWEwbG1xOW13aWhjbHE2dWZ3cjhpcyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/QU4ewgcmdcsObx9CG7/giphy.gif",
    # Happy Gilmore
    "https://media1.tenor.com/m/Eo79iCWoTMEAAAAd/happy-gilmore-adam-sandler.gif",
    "https://media1.tenor.com/m/Yfd-zivMy14AAAAd/happy-gilmore-adam-sandler.gif",
    "https://media1.tenor.com/m/WnDaDK6CKHoAAAAd/happy-gilmore-adam.gif",
    "https://media1.tenor.com/m/ZZFz0DZ_V-kAAAAd/adam-sandler-happy-gilmore.gif",
    "https://media1.tenor.com/m/wNDfmw4_DxkAAAAd/adam-sandler.gif",
    "https://media1.tenor.com/m/XDg3Fhmc1_4AAAAd/adam-sandler-im-sorry.gif",
    "https://media1.tenor.com/m/162NshPMNkEAAAAd/embarrassing-hahaha.gif",
    "https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExOHBnN3B0MG00N3d3M3BmNDRqaXYwN2dvbTNvYmY1aHc1bWd4dGpqcCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/j0gPbtGBftZWDW8z7p/giphy.gif",
    "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExejVuOW9paXk4MnhucGhqbXEyMmlqeWcxOXV3OGQzMjE4aG9oY2R4cCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/2Xflxzwcpn1eYI03dXq/giphy.gif",
    # Billy Madison
    "https://media1.tenor.com/m/LTOP6Kd5bGQAAAAd/adam-sandler-billy-madison.gif",
    "https://media1.tenor.com/m/K1ftfYVWQMcAAAAd/adam-sandler-billy-madison.gif",
    "https://media1.tenor.com/m/v9az3-qUgBEAAAAd/adam-sandler-billy-madison.gif",
    "https://media1.tenor.com/m/zRlPFqDjQh4AAAAd/billy-madison-adam-sandler.gif",
    "https://media1.tenor.com/m/o_5e1G8ZYKMAAAAd/billy-madison-adam-sandler.gif",
    "https://media1.tenor.com/m/g8VAj77aYdkAAAAd/billy-madison-adam-sandler.gif",
    "https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExdW9rcnlsNnlnYm9vN29iMWJ3dmk5MTVsOGhhZWwzcjlxdGc1ZjhqNyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/26n6ISkgbxqUCZTji/giphy.gif",
    # Big Daddy
    "https://media1.tenor.com/m/wST_RBtLd58AAAAd/adam-sandler-shouting.gif",
    "https://media1.tenor.com/m/nHcs2Lc-U2kAAAAd/adam-sandler-alright.gif",
    "https://media1.tenor.com/m/MwAsmlf4U_MAAAAd/big-daddy-adam-sandler.gif",
    "https://media1.tenor.com/m/xAAip7O8gVcAAAAd/scuba-steve-adam-sandler.gif",
    # The Waterboy
    "https://media1.tenor.com/m/vZw7xZFAQzwAAAAd/thumbs-up-the-waterboy.gif",
    "https://media1.tenor.com/m/mJ29vbyDwBwAAAAd/you-can-do-it-rob-schneider.gif",
    "https://media1.tenor.com/m/r5IeprtIP2kAAAAd/waterboy-rob-schneider.gif",
    "https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExMnV4Ym9jcGxzc200ZWx1bzh5OHIwaWo5c2UxZndoZmJkeGhwamJoaSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/KzVuyKpu96qqZWVw70/giphy.gif",
    # The Wedding Singer
    "https://media1.tenor.com/m/NpYrEMRoN6EAAAAd/the-wedding-singer-adam-sandler.gif",
    "https://media1.tenor.com/m/8uvUg_DhEcgAAAAd/wedding-singer.gif",
    # 50 First Dates
    "https://media1.tenor.com/m/SCtsfkyLQ9kAAAAd/50-first.gif",
    "https://media1.tenor.com/m/RJcbtKiwwD0AAAAd/adam-sandler-fifty-first-dates.gif",
    "https://media1.tenor.com/m/oGDuGRzv284AAAAd/50first-dates-adam-sandler.gif",
    "https://media1.tenor.com/m/avK27MyazicAAAAd/50first-dates-adam-sandler.gif",
    # Mr. Deeds
    "https://media1.tenor.com/m/vs6G3mTOKhMAAAAd/byob-adam-sandler.gif",
    # Grown Ups
    "https://media1.tenor.com/m/wZdnFo7hrREAAAAd/adam-sandler-grown-ups.gif",
    "https://media1.tenor.com/m/1Kjs56iN_ccAAAAd/grown-ups-adam-sandler.gif",
    "https://media1.tenor.com/m/oIq7d03t2KMAAAAd/grown-ups-yes.gif",
    "https://media1.tenor.com/m/wRGAkFkUFx8AAAAd/grown-ups-dave-spade.gif",
    "https://media1.tenor.com/m/eR7eoi88uOUAAAAd/grown-ups-adam-sandler.gif",
    # The Longest Yard
    "https://media1.tenor.com/m/Vw80qaiq2y4AAAAd/the-longest.gif",
    "https://media1.tenor.com/m/pAkp-MlHWK8AAAAd/longest-yard-adam-sandler.gif",
    "https://media1.tenor.com/m/vGsBaysFAsAAAAAd/longest-yard-football.gif",
    # Click
    "https://media1.tenor.com/m/yRALapPMOwAAAAAd/click-adam-sandler.gif",
    "https://media1.tenor.com/m/64EeAnS4pUMAAAAd/adam-sandler-click.gif",
    # Murder Mystery
    "https://media1.tenor.com/m/h91sUzU6zVEAAAAd/cheese-hold-this-cheese-has-a-hold-on-me.gif",
    "https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExNGt5OHZjMXg5eWs0a2FmMXdzNmI5cWRyNjR0MmQwY2xkbGFweWNjbSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/hSLpnunLN855ICgRf3/giphy.gif",
    "https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExeDNyNThhMjltd2t4aXVxYWdkcTVoMjdmc2MxejU5ZnJ5ZDh6a2FscSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/UVeTwpgaUZrj958bqR/giphy.gif",
    # Hotel Transylvania
    "https://media1.tenor.com/m/yrcCnO-qLn8AAAAd/hotel-transylvania-adam-sandler.gif",
    "https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExOTZyMGZwbWwzazdva3o1empmcTZzanE0MW56dXUwaDRlbXI4eGpmNSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/Rus46dbY3YK0U/giphy.gif",
    "https://media3.giphy.com/media/v1.Y2lkPTc5MGI3NjExNGdqbWIyNW13bDI5cm54ZjBhcDlxZDFwdXA5ZHE1bDcxMm1wNWV2NyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/ZOB4mq6qck4b477mNB/giphy.gif",
    "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExYnhnZjh0dXBoZnlkbGk4dDRqcHkxeTFidXkwbXRyc2txaDI1eDFyciZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/CEAMckbSd9lPrI5tDy/giphy.gif",
    # Anger Management
    "https://media1.tenor.com/m/UnSywpETjTwAAAAd/adam-sandler-anger-management.gif",
    # Hubie Halloween
    "https://media1.tenor.com/m/12u7Fkpc0joAAAAd/wink-hubie-dubois.gif",
    "https://media1.tenor.com/m/UIvpnSCxpXMAAAAd/on-it-hubie-dubois.gif",
    # Little Nicky
    "https://media1.tenor.com/m/NE_iJlrEK4UAAAAd/little-nicky-adam-sandler.gif",
    # Pixels
    "https://media1.tenor.com/m/f37aW-BekM8AAAAd/adam-sandler-pixels.gif",
    # General / SNL
    "https://media1.tenor.com/m/G9Ai9Ty_vmQAAAAd/adam-sandler-laughing-hysterically.gif",
    "https://media1.tenor.com/m/ADwdegnn87cAAAAd/adam-sandler-laughing-hysterically.gif",
    "https://media1.tenor.com/m/Exi3gJ7degMAAAAd/adam-sandler-laughing.gif",
    "https://media1.tenor.com/m/LLAEosAQG14AAAAd/money-dance-happy-dance.gif",
    "https://media1.tenor.com/m/g_5VNFbAcasAAAAd/adam-sandler-happy.gif",
    "https://media1.tenor.com/m/dLgTTv8nTqMAAAAd/adam-sandler-gangnam-style.gif",
    "https://media1.tenor.com/m/daYmFXR3WucAAAAd/david-spade-adam-sandler.gif",
    "https://media1.tenor.com/m/QuftLo2Sr4oAAAAd/adam-sandler-snl.gif",
    "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExMmphZXB4cXg3eTl3ZGF2dmxqZDluM3F6ZDF2azQ4NGNiNXhwaXBlMSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/26ueZpF95CyH5sWY0/giphy.gif",
    "https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExbW9jZDZ0eXU1OWo5N2l3eXI3NWl1amRhY3ozNnFpc2NvdWxyanhhNSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/vILMNs7bqbylbhDbTs/giphy.gif",
    "https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExbHh4bnRxcjN2OXljbm91NGx5and4eWV2dWVlcGNraXhmcTM0aGhjYSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/kdQkf3DRUqAms6kS3K/giphy.gif",
    "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExbThzbnRwMmEzb2VlcmFhMWNwcHh0ZnF3NzFpNmxiZzhpMG02NDhpdCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/3oz8xCN6oqq4CUMs1i/giphy.gif",
]

FINDINGS_QUOTES = [
    # Uncut Gems
    "This is how I win.",
    "I'm so f**kin' far from worried, you have no idea.",
    "Everything I do is not as crazy as it seems.",
    "No, this is me. This is how I win.",
    "You wanna bet? You wanna f**kin' bet?",
    "I just made a really big bet and I need you to trust me.",
    "I'm not gonna f**k this up.",
    "I got it under control.",
    "I know what I'm doing!",
    "This is the kind of s**t I do, Arno.",
    "I got a system.",
    "It's all coming together.",
    "I'm the one with the touch. I'm the one who's magic.",
    "You think I don't know what I got here?",
    "When you do it right, it's not gambling.",
    "Trust the process.",
    "Hold on, hold on, hold on — just listen to me.",
    "I'm gonna win. I always win.",
    # Happy Gilmore
    "The price is wrong, b**ch.",
    "I eat pieces of s**t like you for breakfast.",
    "Just tap it in. Just tap it in. Give it a little tappy.",
    "It's all in the hips. It's all in the hips.",
    "You're gonna die, clown!",
    "You will not make this putt, you jackass!",
    "I'm stupid. You're smart. I was wrong. You were right. You're the best. I'm the worst.",
    "Go to your home! Are you too good for your home?!",
    "During high school, I played junior hockey and still hold two league records: most time spent in the penalty box, and I was the only guy to ever take off his skate and try to stab somebody.",
    # Billy Madison
    "Back to school. Back to school, to prove to Dad that I'm not a fool.",
    "It's too damn hot for a penguin to be just walkin' around here.",
    "That Veronica Vaughn is one piece of ace.",
    "Shampoo is better. I go on first and clean the hair.",
    "If peeing your pants is cool, consider me Miles Davis.",
    "Stop looking at me, swan!",
    "I am the smartest man alive!",
    "What you just said is one of the most insanely idiotic things I have ever heard. At no point in your rambling, incoherent response were you even close to anything that could be considered a rational thought.",
    # The Waterboy
    "You can do it!",
    "My mama says that alligators are ornery because they got all them teeth and no toothbrush.",
    "Now that's what I call high-quality H2O.",
    "I invented electricity. Ben Franklin is the devil!",
    "Mama said knock you out!",
    "Captain Insano shows no mercy.",
    "That's some high-quality H2O.",
    "No Colonel Sanders, you're wrong. Mama's right.",
    # Big Daddy
    "But I wipe my own a**! I wipe my own a**!",
    "Hip? Hip-hop? Hip-hop-anonymous?",
    "I'm a big kid now.",
    "If you want him to have a healthy attitude about food, just let him pick.",
    # Anger Management
    "Temper's the one thing you can't get rid of by losing it.",
    "In a world where you can be anything, be calm.",
    "I feel pretty. Oh so pretty.",
    "Sarcasm is anger's ugly cousin.",
    # The Wedding Singer
    "I have a microphone and you don't, so you will listen to every damn word I have to say!",
    "Once again, things that could have been brought to my attention YESTERDAY!",
    "Somebody kill me, please! ...I'm kidding, I'm fine. Let's review some code.",
    "They were cones!",
    "I'm a big fan of money. I like it. I use it. I have a little. I keep it in a jar on top of my refrigerator.",
    # Click
    "Family comes first. Always has, always will.",
    "This is my remote. It controls my universe.",
    "Will I ever learn? Of course not, but that's what makes me me.",
    "Fast-forward through the bad parts? Buddy, the bad parts are what make the good parts good.",
    # Hustle
    "I don't need you to believe in me. I need you to believe in yourself.",
    "Hard work beats talent when talent doesn't work hard.",
    "You got the fire, kid. Don't let anybody put it out.",
    "Everybody has a ceiling. I'm just trying to raise mine.",
    "I'm not asking you to be perfect. I'm asking you to be relentless.",
    # The Longest Yard
    "Winners always want the ball when the game is on the line.",
    # 50 First Dates
    "The best part about finding out you love someone is doing it all over again every day.",
    # You Don't Mess with the Zohan
    "Don't mess with the Zohan.",
    "I am the Zohan! I do not lose!",
    # Mr. Deeds
    "I'm gonna keep doin' what I think is right.",
    "Sneaky, sneaky, sir.",
]

FAILED_QUOTES = [
    # Uncut Gems
    "I gotta get the stone back.",
    "This is not how this was supposed to go.",
    "I'm in a lot of trouble here.",
    "Everything is falling apart and nobody gives a s**t.",
    "I need more time. Just a little more time.",
    "It's over. It's all f**kin' over.",
    "I'm f**ked, I'm totally f**ked.",
    "You don't understand, this was a sure thing.",
    "I had it, I had the whole thing, and it just...",
    "Arno, please. Please, Arno.",
    "I can fix this. I can fix all of this.",
    "Give me another shot.",
    "Don't do this to me. Don't f**kin' do this to me.",
    "Where's my ring? Where's my f**kin' ring?",
    "How did this happen? How did we get here?",
    "This is really, really bad.",
    "I'm drowning here. I'm f**kin' drowning.",
    # Happy Gilmore
    "You're in big trouble, pal. I eat pieces of s**t like you for breakfast.",
    "I blew it. I totally blew it.",
    "The gold jacket's mine. ...Actually no, it's not.",
    "This guy's driving me crazy. And not in the fun way.",
    # Billy Madison
    "Mr. Madison, what you've just said is one of the most insanely idiotic things I have ever heard. Everyone in this room is now dumber for having listened to it.",
    "No I will not make out with you! ...I mean, I'm failing here.",
    "I don't know. I really don't know.",
    "I'm not gonna pass. I'm not gonna pass. Oh my God, I'm not gonna pass.",
    "That is correct.",
    # The Waterboy
    "Mama, somethin' bad happened today.",
    "Something is wrong with his medulla oblongata!",
    "You don't have what they call 'the social skills.'",
    "Gatorade not only quenches your thirst better, it tastes better too. ...Wait, that's not right.",
    "Everything is the devil to you, Mama!",
    # Big Daddy
    "I was not aware of that rule.",
    "I got a feeling we're not gonna be able to fix this one with a Happy Meal.",
    "I don't even know what day it is.",
    "I'm 32 years old and I have nothing to show for it.",
    # Click
    "I just wanna rewind. Can I please just rewind?",
    "I fast-forwarded through everything that mattered.",
    "You can't skip the hard parts. That's where all the good stuff is.",
    "I missed it. I missed the whole damn thing.",
    "Where did the time go?",
    # Anger Management
    "I think... I have a problem.",
    "I'm calm. I'm totally calm. DOES THIS LOOK CALM TO YOU?!",
    # The Wedding Singer
    "He's losing his mind... and I'm reaping all the benefits.",
    "Love stinks. Yeah yeah.",
    # 50 First Dates
    "I don't remember any of this.",
    # Grown Ups
    "I don't even know what I'm doing anymore.",
    "I think we all just collectively gave up.",
    # The Longest Yard
    "We're gettin' killed out there and I don't know how to stop it.",
]

FRAGMENT_FILES = [
    "/tmp/trivy-fragment.md",
    "/tmp/size-fragment.md",
    "/tmp/deps-fragment.md",
]


def get_sign_off(outcome, diff):
    seed = int.from_bytes(hashlib.md5(diff.encode()).digest(), "big")
    rng = random.Random(seed)
    if outcome == "clean":
        gif = rng.choice(CLEAN_GIFS)
        return f"\n---\n\n![Uncut Gems]({gif})"
    pool = FAILED_QUOTES if outcome == "failed" else FINDINGS_QUOTES
    quote = rng.choice(pool)
    return f'\n---\n\n> *"{quote}"* — Adam Sandler'


def read_fragments():
    sections = []
    for path in FRAGMENT_FILES:
        try:
            with open(path) as f:
                content = f.read().strip()
                if content:
                    sections.append(content)
        except FileNotFoundError:
            continue
    return sections


def filter_diff(diff_text, exclude_patterns):
    if not exclude_patterns:
        return diff_text
    kept = []
    keep = True
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git"):
            path = diff_path(line)
            base = path.rsplit("/", 1)[-1]
            keep = not any(
                fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(base, pat)
                for pat in exclude_patterns
            )
        if keep:
            kept.append(line)
    return "".join(kept)


def diff_path(header):
    # Git quotes UTF-8 as C-style octal bytes, not Unicode escapes.
    match = re.fullmatch(r'diff --git ("(?:[^"\\]|\\.)*"|a/.*?) ("(?:[^"\\]|\\.)*"|b/.*)', header.rstrip("\n"))
    if not match:
        raise ValueError("Unrecognized diff header")
    path = match.group(2)
    if path.startswith('"'):
        inner = "".join(char if ord(char) < 128 else "".join(f"\\{byte:03o}" for byte in char.encode("utf-8")) for char in path[1:-1])
        path = ast.literal_eval('b"' + inner + '"').decode("utf-8")
    if not path.startswith("b/"):
        raise ValueError("Invalid destination path")
    return path[2:]


def parse_diff_ranges(diff_text):
    ranges = {}
    current_file = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            current_file = diff_path(line)
            ranges.setdefault(current_file, [])
            new_line = None
        elif line.startswith("@@") and current_file:
            hunk = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if hunk:
                start = int(hunk.group(1))
                count = int(hunk.group(2)) if hunk.group(2) else 1
                new_line = start
        elif current_file and new_line is not None:
            if line.startswith("+"):
                spans = ranges[current_file]
                if spans and spans[-1][1] == new_line - 1:
                    spans[-1] = (spans[-1][0], new_line)
                else:
                    spans.append((new_line, new_line))
                new_line += 1
            elif line.startswith(" "):
                new_line += 1
    return ranges


def validate_findings(findings, valid_ranges, audit=None):
    audit = audit if audit is not None else {"rejected": [], "duplicates": 0}
    validated = []
    seen = set()
    for index, f in enumerate(findings):
        reason = finding_error(f, valid_ranges)
        if reason:
            audit["rejected"].append({"index": index, "reason": reason})
            continue
        key = json.dumps(f, sort_keys=True)
        if key in seen:
            audit["duplicates"] += 1
            continue
        seen.add(key)
        validated.append(dict(f))
    return validated


def finding_error(f, valid_ranges):
    if not isinstance(f, dict):
        return "finding-not-object"
    required = {"file", "line", "severity", "description"}
    if not required <= f.keys() or f.keys() - required - {"start_line", "suggested_fix"}:
        return "finding-fields"
    if not isinstance(f["severity"], str) or f["severity"] not in SEVERITY_RANK or not isinstance(f["description"], str) or not f["description"].strip():
        return "finding-content"
    if "```" in f["description"] or "~~~" in f["description"]:
        return "description-fence"
    path, line = f["file"], f["line"]
    if not isinstance(path, str) or type(line) is not int or line < 1:
        return "finding-location"
    spans = valid_ranges.get(path, [])
    start = f.get("start_line", line)
    if type(start) is not int or start < 1 or start > line:
        return "invalid-span"
    if not any(s <= start <= line <= e for s, e in spans):
        return "unchanged-or-outside-span"
    fix = f.get("suggested_fix")
    if fix is not None:
        if not isinstance(fix, str) or not fix or "```" in fix or "~~~" in fix:
            return "invalid-suggestion"
        # Conservative bounded pass: multi-line replacements require a separate
        # source-aware validator. Never narrow their replacement range silently.
        if start != line or "\n" in fix or "\r" in fix or len(fix.encode()) > 4096:
            return "unsafe-suggestion-span"
    return None


def format_comment_body(finding):
    sev = finding.get("severity", "NIT")
    icon = SEVERITY_ICON.get(sev, "⚪")
    body = f"**{icon} {sev}**\n\n{finding['description']}"
    fix = finding.get("suggested_fix")
    if fix:
        if not isinstance(fix, str) or "```" in fix or "~~~" in fix or "\n" in fix or "\r" in fix or len(fix.encode()) > 4096:
            raise ValueError("Unsafe suggestion")
        body += f"\n\n```suggestion\n{fix}\n```"
    return body


def build_failure_payload(reason, is_incremental, sha, fragments, diff=""):
    body_parts = ["## Uncut Gemini", ""]

    if is_incremental:
        body_parts.append(f"*Incremental review — commits since `{sha[:7]}`*")
        body_parts.append("")

    for fragment in fragments:
        body_parts.append(fragment)
        body_parts.append("")

    body_parts.append("### 🔍 Code Review — failed")
    body_parts.append("")
    body_parts.append(f"Gemini review did not complete: {reason}")
    body_parts.append("")
    body_parts.append("See the workflow logs for details. Trivy and PR-stats results above are unaffected.")
    body_parts.append(get_sign_off("failed", diff))

    return {
        "event": "COMMENT",
        "body": "\n".join(body_parts),
        "comments": []
    }


def build_review_payload(findings, summary, is_incremental, sha, fragments, diff=""):
    body_parts = ["## Uncut Gemini", ""]

    if is_incremental:
        body_parts.append(f"*Incremental review — commits since `{sha[:7]}`*")
        body_parts.append("")

    for fragment in fragments:
        body_parts.append(fragment)
        body_parts.append("")

    if not findings:
        body_parts.append("### 🔍 Code Review — clean")
        body_parts.append("")
        body_parts.append(summary)
        body_parts.append(get_sign_off("clean", diff))
        return {
            "event": "COMMENT",
            "body": "\n".join(body_parts),
            "comments": []
        }

    high = sum(1 for f in findings if f.get("severity") == "HIGH")
    med = sum(1 for f in findings if f.get("severity") == "MEDIUM")
    nit = sum(1 for f in findings if f.get("severity") == "NIT")
    counts = ", ".join(p for p in [
        f"{high} high" if high else "",
        f"{med} medium" if med else "",
        f"{nit} nit" if nit else "",
    ] if p)

    noun = "finding" if len(findings) == 1 else "findings"
    body_parts.append(f"### 🔍 Code Review — {len(findings)} {noun} ({counts})")
    body_parts.append("")
    body_parts.append(summary)
    body_parts.append("")
    body_parts.append("See inline comments below for details.")
    body_parts.append(get_sign_off("findings", diff))

    comments = []
    for f in sorted(findings, key=lambda x: SEVERITY_RANK.get(x.get("severity", "NIT"), 3)):
        comment = {
            "path": f["file"],
            "line": f["line"],
            "side": "RIGHT",
            "body": format_comment_body(f)
        }
        start_line = f.get("start_line")
        if isinstance(start_line, int) and start_line < f["line"]:
            comment["start_line"] = start_line
            comment["start_side"] = "RIGHT"
        comments.append(comment)

    return {
        "event": "COMMENT",
        "body": "\n".join(body_parts),
        "comments": comments
    }


SCHEMA_INSTRUCTIONS = """Response schema:
{
  "verdict": "clean | findings",
  "summary": "one sentence overall assessment",
  "findings": [
    {
      "severity": "HIGH | MEDIUM | NIT",
      "file": "relative/path",
      "line": 42,
      "start_line": 38,
      "description": "what and why",
      "suggested_fix": "the corrected replacement code or null"
    }
  ]
}

Line number rules:
- "line" is REQUIRED — the line number in the NEW version of the file
- Count from diff hunk headers: @@ -old,count +new_start,count @@
- Lines prefixed with "+" or " " (space) are in the new file — count those from new_start
- Lines prefixed with "-" are old-file only — do not count them
- For multi-line findings, set "start_line" to the first line and "line" to the last line
- Omit "start_line" for single-line findings

Suggested fix rules:
- "suggested_fix" is the corrected code that REPLACES lines from start_line to line
- Provide raw code only — no markdown fences, no surrounding context
- Must be syntactically complete for the replaced range
- Set to null if no concrete fix exists or if the fix spans multiple locations"""


def build_prompt(diff, guidelines, extra_instructions="", incremental=False,
                 last_reviewed_sha="", full_diff=""):
    today = datetime.date.today().isoformat()
    preamble = (
        f"You are a code reviewer. Today's date is {today}. Review this pull request "
        "diff for bugs, logic errors, race conditions, security vulnerabilities, "
        "data-integrity and stability risks, and convention compliance."
    )
    if incremental:
        preamble += (
            f"\n\nThis is an incremental review of commits since {last_reviewed_sha[:7]}. "
            "Focus exclusively on new and modified code."
        )

    prompt = f"""{preamble}

RULES:
- Only review changed lines (+ prefixed in the diff) — do not flag pre-existing issues
- Examine every changed file and report every genuine issue, not just the first one you find
- The diff shows only changed hunks, not whole files. Never claim an import, definition, or symbol is missing based only on its absence from the diff — it may exist in unchanged code
- Do not suggest version upgrades, package migrations, or specific version numbers for ANY dependency (GitHub Actions, npm, pip, Docker images, etc.) — you lack real-time knowledge of releases and your suggestions may be incorrect, outdated, or nonexistent
- Never claim a specific version fixes a vulnerability unless the fix version is explicitly stated in the diff itself
- Return ONLY a JSON object — no markdown fences, no explanation
- If no issues found, return: {{"verdict": "clean", "summary": "one sentence", "findings": []}}

{SCHEMA_INSTRUCTIONS}

Severity guide:
- HIGH: Bug that produces wrong results or crashes, security vulnerability, data loss or corruption risk, breaking change
- MEDIUM: Race condition, unhandled edge case, stability concern, missing safety check, convention violation
- NIT: Minor improvement — only include if truly worth mentioning

<conventions>
{guidelines}
</conventions>
"""
    if extra_instructions:
        prompt += f"""
<extra-instructions>
{extra_instructions}
</extra-instructions>
"""
    prompt += f"""
<diff>
{diff}
</diff>"""
    if incremental and full_diff:
        prompt += f"""

The <diff> above contains only the commits being reviewed. The full PR diff is provided below as read-only context for imports, definitions, and related changes. Report findings ONLY for lines in <diff>.
<full-pr-diff>
{full_diff}
</full-pr-diff>"""
    return prompt


def build_generation_config(model, diff_line_count):
    # Gemini 3.x uses thinkingLevel and degrades if temperature is lowered below
    # 1.0; Gemini 2.5 has no thinkingLevel and benefits from low temperature for
    # deterministic JSON. Branch so an overridden 2.5 model still works.
    if model.startswith("gemini-3"):
        level = "high" if diff_line_count > THINKING_HIGH_DIFF_LINES else "medium"
        return {"thinkingConfig": {"thinkingLevel": level}}
    return {"temperature": 0.1}


def main():
    from runtime import run
    run()


if __name__ == "__main__":
    main()
