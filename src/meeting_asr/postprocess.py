"""Build display turns without changing the raw ASR evidence."""

from __future__ import annotations

import re

from meeting_asr.models import Turn, Utterance


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
