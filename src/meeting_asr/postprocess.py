"""Build display turns without changing the raw ASR evidence."""

from __future__ import annotations

import re

from meeting_asr.models import Turn, Utterance

WORDS = ("", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín")


def spoken_number(number):
    if number < 10:
        return WORDS[number]
    tens, ones = divmod(number, 10)
    prefix = "mười" if tens == 1 else f"{WORDS[tens]} mươi"
    suffix = "lăm" if ones == 5 else ("mốt" if ones == 1 and tens > 1 else WORDS[ones])
    return prefix + (f" {suffix}" if suffix else "")


def normalize_dates(text):
    numbers = {spoken_number(n): n for n in range(1, 32)}
    alternatives = "|".join(sorted(numbers, key=len, reverse=True))
    pattern = rf"\b({alternatives})\s+tháng\s+({alternatives})\b"

    def replace(match):
        day, month = numbers[match[1].casefold()], numbers[match[2].casefold()]
        days = (0, 31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
        return f"{day}/{month}" if month <= 12 and day <= days[month] else match[0]

    return re.sub(pattern, replace, text, flags=re.IGNORECASE)


def _is_short(utterance: Utterance) -> bool:
    return len(utterance.text.split()) <= 2 and utterance.duration <= 1.5


def backchannels(ordered: list[Utterance], merge_gap: float) -> set[int]:
    """Indexes of short interjections ("ừ", "ok") of one speaker inside another's continuing speech.

    On real meetings these split the main speaker into many fragments (half of all turns < 1.5 s).
    """
    found, last_kept = set(), None
    for i, utterance in enumerate(ordered):
        prev = ordered[last_kept] if last_kept is not None else None
        if prev is not None and utterance.speaker != prev.speaker and _is_short(utterance):
            j = i + 1
            while j < len(ordered) and ordered[j].speaker != prev.speaker and _is_short(ordered[j]):
                j += 1
            if (
                j < len(ordered)
                and ordered[j].speaker == prev.speaker
                and ordered[j].start - prev.end <= merge_gap
            ):
                found.add(i)
                continue
        last_kept = i
    return found


def postprocess(utterances: list[Utterance], merge_gap=0.8, remove_fillers=False) -> list[Turn]:
    if merge_gap < 0:
        raise ValueError("merge_gap must be nonnegative")
    ordered = sorted(utterances, key=lambda u: (u.start, u.end, u.speaker))
    aside = backchannels(ordered, merge_gap)
    groups: list[list[Utterance]] = []
    for index, utterance in enumerate(ordered):
        if index in aside:
            continue
        if (
            groups
            and groups[-1][-1].speaker == utterance.speaker
            and (utterance.start - max(u.end for u in groups[-1]) <= merge_gap)
        ):
            groups[-1].append(utterance)
        else:
            groups.append([utterance])
    # Interjections stay as their own turns, in time order, without breaking the main speaker.
    groups += [[ordered[i]] for i in aside]
    aside_ids = {id(ordered[i]) for i in aside}
    groups.sort(key=lambda g: (g[0].start, g[0].end, g[0].speaker))
    turns = []
    for index, group in enumerate(groups):
        text = " ".join(u.text.strip() for u in group if u.text.strip())
        text = normalize_dates(text)
        if remove_fillers:
            text = re.sub(r"\b(?:ừ|à|kiểu)\b", "", text, flags=re.IGNORECASE)
            text = " ".join(text.split())
        text = text[:1].upper() + text[1:]
        turns.append(
            Turn(
                f"turn_{index:05d}",
                group[0].start,
                max(u.end for u in group),
                group[0].speaker,
                text,
                list(group),
                backchannel=id(group[0]) in aside_ids,
            )
        )
    return turns
