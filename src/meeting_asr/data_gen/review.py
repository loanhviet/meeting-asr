"""Portable listening package; verification is an explicit action by a reviewer."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from meeting_asr.data_gen.annotations import validate_speech_labels
from meeting_asr.data_gen.simulate import read_mono_wav
from meeting_asr.io import _atomic_text
from meeting_asr.runtime import file_sha256


def build_speech_review(manifest, out):
    source, destination = Path(manifest).resolve(), Path(out).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    clips = []
    for entry in payload["clips"]:
        wav = (source.parent / entry["wav"]).resolve()
        checksum = file_sha256(wav)
        if entry.get("sha256", checksum) != checksum:
            raise ValueError(f"audio checksum mismatch: {entry['clip_id']}")
        waveform, sr = read_mono_wav(wav)
        duration = len(waveform) / sr
        intervals = entry.get("speech_intervals", entry.get("proposed_intervals"))
        annotation = entry.get("speech_annotation") or {
            "status": "automatic_unverified",
            "method": "full-clip-review-candidate"
            if intervals is None
            else "conservative-vad-consensus",
            "version": "v1",
        }
        intervals = intervals if intervals is not None else [[0, duration]]
        validate_speech_labels(intervals, annotation, duration)
        name = f"audio/{checksum}.wav"
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or file_sha256(target) != checksum:
            shutil.copyfile(wav, target)
        clips.append(
            {
                **entry,
                "wav": name,
                "duration": duration,
                "sha256": checksum,
                "speech_intervals": intervals,
                "speech_annotation": annotation,
            }
        )
    review = {"schema_version": 1, "manifest_sha256": file_sha256(source), "clips": clips}
    _atomic_text(destination / "labels.json", json.dumps(review, ensure_ascii=False, indent=2))
    # Escape script terminators in transcript text. All displayed data uses textContent.
    data = json.dumps(review, ensure_ascii=False).replace("<", "\\u003c")
    _atomic_text(destination / "index.html", PAGE.replace("__DATA__", data))
    return {"clips": len(clips), "page": str(destination / "index.html")}


PAGE = r"""<!doctype html><html lang="vi"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Soát nhãn tiếng nói</title>
<style>body{font:16px system-ui;max-width:850px;margin:30px auto;padding:0 16px;background:#f7f8fa;color:#182030}section{background:white;border:1px solid #ddd;padding:20px;margin:18px 0;border-radius:12px}audio,textarea{width:100%}textarea{min-height:70px}button,input{font:inherit;padding:8px;margin:6px 4px 6px 0}label{display:block}#status{position:sticky;top:0;background:#f7f8fa;padding:12px}small{display:block;color:#555}</style>
<h1>Nghe và xác nhận nhãn tiếng nói</h1>
<p>Nghe clip gốc, chỉnh các khoảng [bắt đầu, kết thúc] tính bằng giây. Giữ lời nói nhỏ và kiểm tra khoảng dừng giữa câu. Chỉ bấm xác nhận sau khi đã nghe. Audio không bị cắt; các khoảng này dùng để chấm phân người nói.</p>
<label>Người soát <input id="reviewer" placeholder="Tên người nghe"></label>
<button id="download">Tải nhãn đã soát</button><div id="status" role="status"></div><main id="clips"></main>
<script>
const data=__DATA__, key='speech-review:'+data.manifest_sha256;
let saved={};try{saved=JSON.parse(localStorage.getItem(key)||'{}')}catch{}
const state=data.clips.map(c=>saved[c.sha256]||c);
const update=()=>{document.querySelector('#status').textContent=state.filter(c=>c.speech_annotation.status==='human_verified').length+'/'+state.length+' clip đã xác nhận';try{localStorage.setItem(key,JSON.stringify(Object.fromEntries(state.map(c=>[c.sha256,c]))))}catch{}};
for(const c of state){
const section=document.createElement('section');const title=document.createElement('h2');title.textContent=c.clip_id+' — '+c.speaker;
const text=document.createElement('p');text.textContent=c.text;
const audio=document.createElement('audio');audio.controls=true;audio.preload='none';audio.src=c.wav;
const input=document.createElement('textarea');input.value=JSON.stringify(c.speech_intervals);input.setAttribute('aria-label','Khoảng tiếng nói '+c.clip_id);
const note=document.createElement('input');note.placeholder='Ghi chú';note.value=c.speech_annotation.notes||'';note.setAttribute('aria-label','Ghi chú '+c.clip_id);
const message=document.createElement('small');message.textContent=c.speech_annotation.status;
const confirm=document.createElement('button');confirm.textContent='Đã nghe — xác nhận nhãn';
const dirty=()=>{if(c.speech_annotation.status==='human_verified'){c.speech_annotation={status:'automatic_unverified',method:'manual-edit-pending-review',version:'v1'}}message.textContent='Có chỉnh sửa, cần xác nhận lại';update()};input.oninput=dirty;note.oninput=dirty;
confirm.onclick=()=>{try{const reviewer=document.querySelector('#reviewer').value.trim();if(!reviewer)throw Error('Điền tên người soát.');const ranges=JSON.parse(input.value);let end=-1;if(!Array.isArray(ranges)||!ranges.length)throw Error('Cần ít nhất một khoảng.');for(const r of ranges){if(!Array.isArray(r)||r.length!==2||r.some(x=>typeof x!=='number'||!Number.isFinite(x))||r[0]<0||r[0]>=r[1]||r[1]>c.duration||r[0]<end)throw Error('Khoảng phải tăng dần, không chồng nhau và nằm trong clip.');end=r[1]}c.speech_intervals=ranges;c.speech_annotation={status:'human_verified',method:'manual-listening',version:'v1',reviewed_by:reviewer,reviewed_at:new Date().toISOString(),notes:note.value.trim()};message.textContent='Đã xác nhận';update()}catch(e){message.textContent=e.message}};
section.append(title,text,audio,input,note,confirm,message);document.querySelector('#clips').append(section);
}
document.querySelector('#download').onclick=()=>{const blob=new Blob([JSON.stringify({...data,clips:state},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='speech-labels.reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};update();
</script></html>"""
