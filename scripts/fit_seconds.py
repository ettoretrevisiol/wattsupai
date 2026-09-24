#!/usr/bin/env python3
"""
Download raw Garmin FIT files and compute TRUE per-second time-in-zone.

Supersedes lap-average zone binning, which systematically understates peak
zones (a 10-min lap averaging 150bpm can contain minutes at 170bpm).

Run with the uv-cached env that has garminconnect + fitparse:
  /Users/ettoretr/.cache/uv/archive-v0/ncqKHR0kl2fa6nKpXwaoC/bin/python3 scripts/fit_seconds.py

Outputs:
  data/fit-raw/<activity_id>.fit          raw FIT (local archive, download once)
  data/seconds/<activity_id>.json         per-ride per-second derived metrics
"""
import io, json, os, sys, zipfile, glob, time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW  = os.path.join(ROOT, 'data', 'fit-raw')
SEC  = os.path.join(ROOT, 'data', 'seconds')
ANA  = os.path.join(ROOT, 'data', 'fit-analysis')
os.makedirs(RAW, exist_ok=True)
os.makedirs(SEC, exist_ok=True)

# Ettore's HR zones
def hr_zone(h):
    if h is None: return None
    if h < 130: return 'z1'
    if h < 155: return 'z2'
    if h < 166: return 'z3'
    if h < 180: return 'z4'
    return 'z5'

# Power zones, FTP 256W
FTP = 256
def pw_zone(p):
    if p is None: return None
    if p < 141: return 'p1'
    if p < 193: return 'p2'
    if p < 231: return 'p3'
    if p < 269: return 'p4'
    if p < 308: return 'p5'
    if p < 385: return 'p6'
    return 'p7'


def get_client():
    from garminconnect import Garmin
    g = Garmin()
    g.login(os.path.expanduser('~/.garminconnect'))
    return g


def fetch_fit(g, aid):
    """Download FIT to local archive if not already present."""
    path = os.path.join(RAW, f'{aid}.fit')
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path, 'cached'
    blob = g.download_activity(aid, dl_fmt=g.ActivityDownloadFormat.ORIGINAL)
    if blob[:2] == b'PK':
        z = zipfile.ZipFile(io.BytesIO(blob))
        name = next(n for n in z.namelist() if n.lower().endswith('.fit'))
        data = z.read(name)
    else:
        data = blob
    with open(path, 'wb') as f:
        f.write(data)
    return path, 'downloaded'


def analyse(path, aid):
    """Parse per-second records, compute true time-in-zone."""
    from fitparse import FitFile
    ff = FitFile(path)
    recs = list(ff.get_messages('record'))
    if not recs:
        return None

    hrs, pws, ts = [], [], []
    for r in recs:
        v = {f.name: f.value for f in r}
        ts.append(v.get('timestamp'))
        hrs.append(v.get('heart_rate'))
        pws.append(v.get('power'))

    # sample interval from timestamps (usually 1s, sometimes smart-recording)
    deltas = []
    for a, b in zip(ts, ts[1:]):
        if a and b:
            d = (b - a).total_seconds()
            if 0 < d <= 60:
                deltas.append(d)
    deltas.sort()
    med_dt = deltas[len(deltas)//2] if deltas else 1.0

    hz = {k: 0.0 for k in ['z1','z2','z3','z4','z5']}
    pz = {k: 0.0 for k in ['p1','p2','p3','p4','p5','p6','p7']}
    hr_secs = pw_secs = 0.0

    for i, (h, p) in enumerate(zip(hrs, pws)):
        dt = med_dt
        if i + 1 < len(ts) and ts[i] and ts[i+1]:
            d = (ts[i+1] - ts[i]).total_seconds()
            dt = d if 0 < d <= 60 else med_dt
        z = hr_zone(h)
        if z:
            hz[z] += dt; hr_secs += dt
        q = pw_zone(p)
        if q:
            pz[q] += dt; pw_secs += dt

    hv = [h for h in hrs if h]
    pv = [p for p in pws if p is not None]

    return dict(
        activity_id=aid,
        n_records=len(recs),
        sample_interval_s=round(med_dt, 2),
        hr_seconds_total=round(hr_secs),
        hr_time_in_zone_s={k: round(v) for k, v in hz.items()},
        hr_min=min(hv) if hv else None,
        hr_mean=round(sum(hv)/len(hv), 1) if hv else None,
        hr_max=max(hv) if hv else None,
        has_power=bool(pv),
        power_seconds_total=round(pw_secs),
        power_time_in_zone_s={k: round(v) for k, v in pz.items()} if pv else None,
        power_mean=round(sum(pv)/len(pv), 1) if pv else None,
        power_max=max(pv) if pv else None,
    )


def one(g, aid):
    try:
        path, how = fetch_fit(g, aid)
        res = analyse(path, aid)
        if res is None:
            return aid, 'no-records', None
        res['source'] = how
        with open(os.path.join(SEC, f'{aid}.json'), 'w') as f:
            json.dump(res, f, indent=1)
        return aid, 'ok', res
    except Exception as e:
        return aid, f'ERR {type(e).__name__}: {e}', None


def main():
    ids = []
    for f in glob.glob(os.path.join(ANA, '*.json')):
        d = json.load(open(f))
        a = d.get('activity_id')
        if a: ids.append(int(a))
    ids = sorted(set(ids))

    only_missing = '--all' not in sys.argv
    if only_missing:
        done = {int(os.path.basename(p)[:-5]) for p in glob.glob(os.path.join(SEC, '*.json'))}
        ids = [i for i in ids if i not in done]

    print(f'activities to process: {len(ids)}')
    if not ids:
        print('nothing to do'); return

    g = get_client()
    print('authenticated')

    ok = err = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(one, g, a): a for a in ids}
        for n, fu in enumerate(as_completed(futs), 1):
            aid, status, _ = fu.result()
            if status == 'ok': ok += 1
            else:
                err += 1; print(f'  {aid}: {status}')
            if n % 25 == 0:
                print(f'  ...{n}/{len(ids)}  ok={ok} err={err}  {time.time()-t0:.0f}s')
    print(f'done: ok={ok} err={err} in {time.time()-t0:.0f}s')


if __name__ == '__main__':
    main()
