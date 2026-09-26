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


def postprocess(utterances: list[Utterance], merge_gap=0.8, remove_fillers=False) -> list[Turn]:
    if merge_gap < 0:
        raise ValueError("merge_gap must be nonnegative")
    groups: list[list[Utterance]] = []
    for utterance in sorted(utterances, key=lambda u: (u.start, u.end, u.speaker)):
        if (
            groups
            and groups[-1][-1].speaker == utterance.speaker
            and (utterance.start - max(u.end for u in groups[-1]) <= merge_gap)
        ):
            groups[-1].append(utterance)
        else:
            groups.append([utterance])
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
            )
        )
    return turns
