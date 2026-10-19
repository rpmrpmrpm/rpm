"""Gallery stills for the ray-marched visualizers.

Each renderer here is a numpy copy of the fragment shader of one stage (TunnelStage,
KaleidoscopeStage, LatticeStage) plus the screen pass of MarchPass, run over the room that
VizDirector gives for one section. The gallery card is therefore a true picture of the visualizer
and not an approximation. It also allows the shapes to be checked without a GPU when a shader is
changed.

    python3 scripts/make_viz_stills.py tunnel|kaleidoscope|lattice

SECTION, CUT and OUT can be set in the environment to render a different room or to write the
picture to a different path.
"""
import os, sys
import numpy as np
from PIL import Image

W, H, STEPS, TAU = 720, 405, 64, 6.283185307179586
KIND = sys.argv[1]
SECTION, CUT = int(os.environ.get('SECTION', '3')), int(os.environ.get('CUT', '12'))

def hash32(n, which):
    m = np.uint32(0xFFFFFFFF)
    with np.errstate(over='ignore'):
        h = (np.uint32(n) * np.uint32(2654435761) + np.uint32(which) * np.uint32(2246822519)) & m
        h ^= h >> np.uint32(15); h = (h * np.uint32(2246822519)) & m
        h ^= h >> np.uint32(13); h = (h * np.uint32(3266489917)) & m
        h ^= h >> np.uint32(16)
    return h
def h01(n, w): return float(hash32(n, w) & np.uint32(0xFFFFFF)) / float(0x1000000)

folds = round(3 + 6 * h01(SECTION, 21)); arm = 2.2 + 2.6 * h01(SECTION, 22)
twist = 0.05 + 0.30 * h01(SECTION, 23); ring = 1.6 + 2.8 * h01(SECTION, 24)
girth = 0.035 + 0.075 * h01(SECTION, 25); bite = 0.25 + 0.95 * h01(SECTION, 26)
palette = int(hash32(SECTION, 11) % np.uint32(4))
orbit = (h01(CUT, 0) - 0.5) * 2.4; advance = 0.9 + 1.4 * h01(CUT, 1)
fov = 0.55 + 0.45 * h01(CUT, 2); sway = 0.08 + 0.5 * h01(CUT, 3)
beats, pulse, drop = 52.0, 0.55, 0.0
eased = np.floor(beats) + np.sqrt(beats % 1.0)
speed = lambda c: 0.9 + 1.4 * h01(c, 1)
_cut = int(np.floor(beats / 8))
travelled = sum(speed(i) for i in range(_cut)) * 8 + speed(_cut) * (beats - _cut * 8)
bands = np.array([0.62, 0.34, 0.21])

fx, fy = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
uvx, uvy = (fx - 0.5 * W) / H, (fy - 0.5 * H) / H
rng = np.random.default_rng(5)
dither = rng.random((H, W))

def rot(px, py, a):
    c, s = np.cos(a), np.sin(a); return px * c + py * s, -px * s + py * c
def boxd(qx, qy, qz, bx, by, bz):
    qx, qy, qz = np.abs(qx) - bx, np.abs(qy) - by, np.abs(qz) - bz
    return (np.sqrt(np.maximum(qx, 0)**2 + np.maximum(qy, 0)**2 + np.maximum(qz, 0)**2)
            + np.minimum(np.maximum(qx, np.maximum(qy, qz)), 0))
def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)
def wedge(px, py, count):
    sector = TAU / count
    a = np.mod(np.arctan2(py, px) + 0.5 * sector, sector) - 0.5 * sector
    r = np.hypot(px, py); return np.cos(a) * r, np.sin(a) * r
def cutout(px, py, pz, r):
    ax, ay, az = np.abs(px), np.abs(py), np.abs(pz)
    return np.minimum(np.maximum(ax, ay), np.minimum(np.maximum(ay, az), np.maximum(ax, az))) - r

# ---------------- tunnel ----------------
def slab_hash(n, salt): return np.mod(np.sin(n * 41.317 + salt * 7.913) * 24634.6345, 1.0)

def value_noise(px, py, pz):
    ix, iy, iz = np.floor(px), np.floor(py), np.floor(pz)
    fx, fy, fz = px - ix, py - iy, pz - iz
    fx, fy, fz = [f * f * (3 - 2 * f) for f in (fx, fy, fz)]
    n = np.zeros_like(px)
    for i in range(8):
        cx, cy, cz = float(i & 1), float((i >> 1) & 1), float((i >> 2) & 1)
        h = np.mod(np.sin((ix + cx) * 127.1 + (iy + cy) * 311.7 + (iz + cz) * 74.7) * 43758.5453, 1.0)
        wx = (1 - fx) * (1 - cx) + fx * cx
        wy = (1 - fy) * (1 - cy) + fy * cy
        wz = (1 - fz) * (1 - cz) + fz * cz
        n += h * wx * wy * wz
    return n

def grain3(px, py, pz):
    return 0.65 * value_noise(px, py, pz) + 0.35 * value_noise(px * 2.07, py * 2.07, pz * 2.07)

def room(px, py, pz, want_lamp=False):
    bore, pitch, thick = arm * 2.4, ring * 2.6, girth * 4.0
    r = np.maximum(np.hypot(px, py), 1e-4)
    ang = np.arctan2(py, px)
    tube = bore - r
    idx = np.floor(pz / pitch + 0.5)
    qz = pz - idx * pitch
    rib = np.maximum(bore * 0.82 - r, np.abs(qz) - thick * (0.6 + slab_hash(idx, 2.0)))

    around, run = 26.0, pitch * 0.25
    sector = TAU / around
    column = np.floor((ang + np.pi) / sector)
    row = np.floor(pz / run + 0.5)
    hsh = slab_hash(column * 7.0 + row * 13.0, 9.0)
    tall = slab_hash(column * 3.0 + row * 29.0, 17.0)
    across = (np.mod(ang + np.pi + 0.5 * sector, sector) - 0.5 * sector) * r
    along = pz - row * run
    stand = bore * (0.045 + 0.16 * hsh * tall)
    face = bore - stand
    block = np.maximum(np.maximum(face - r, r - bore),
                       np.maximum(np.abs(across) - sector * r * (0.30 + 0.14 * tall),
                                  np.abs(along) - run * (0.26 + 0.16 * hsh)))
    lit = (hsh >= 0.93).astype(float)

    strip = np.maximum(np.abs(r - bore * 0.93) - thick * 0.30, np.abs(qz - pitch * 0.5) - thick * 0.55)
    ring_lit = (slab_hash(idx, 3.0) >= 0.42).astype(float)

    ang2 = slab_hash(idx, 1.0) * TAU + beats * 0.02 * (slab_hash(idx, 5.0) - 0.5)
    qx, qy = rot(px, py, ang2)
    blade = boxd(qx - bore * 0.62, qy, qz, bore * 0.30, thick * 1.6, thick * 0.9)

    d = np.minimum(np.minimum(tube, rib), np.minimum(np.minimum(strip, blade), block))
    if not want_lamp: return d
    lamp = np.maximum(ring_lit * (1 - smoothstep(0.0, thick * 0.5, strip - d)),
                      lit * (1 - smoothstep(0.0, thick * 0.4, block - d)))
    return d, lamp

def travel(rox, roy, roz, rdx, rdy, rdz, steps, start):
    t = start.copy(); alive = np.ones(t.shape, bool); hit = np.zeros(t.shape, bool)
    for _ in range(steps):
        d = room(rox + rdx * t, roy + rdy * t, roz + rdz * t)
        now = alive & (d < 0.0025)
        hit |= now; alive &= ~now & (t < 90.0)
        t = np.where(alive, t + d * 0.85, t)
    return t, hit

def lamp_colour(depth):
    cold = (np.array([0.12, 0.85, 0.30]) if palette < 1.5 else
            np.array([0.20, 0.62, 1.00]) if palette < 2.5 else np.array([0.95, 0.35, 0.55]))
    hot = (np.array([0.45, 1.00, 0.35]) if palette < 1.5 else
           np.array([0.50, 0.85, 1.00]) if palette < 2.5 else np.array([1.00, 0.50, 0.35]))
    near = np.exp(-depth * 0.06)
    band = bands[2] * (1 - near) + bands[0] * near
    m = np.clip(band * 1.6, 0, 1)[..., None]
    return (cold * (1 - m) + hot * m) * (0.25 + 2.6 * band)[..., None]

def render_tunnel():
    travel_z = travelled * 1.6
    rox = np.full((H, W), np.sin(beats * 0.13) * sway)
    roy = np.full((H, W), np.cos(beats * 0.09) * sway)
    n = np.sqrt(uvx**2 + uvy**2 + fov**2)
    rdx, rdy, rdz = uvx / n, uvy / n, np.full_like(uvx, fov) / n
    rdx, rdy = rot(rdx, rdy, orbit * 0.4 + np.sin(beats * 0.07) * sway * 0.25)
    t, hit = travel(rox, roy, travel_z, rdx, rdy, rdz, STEPS, 0.02 + dither * 0.12)

    px, py, pz = rox + rdx * t, roy + rdy * t, travel_z + rdz * t
    _, lamp = room(px, py, pz, True)
    e = 0.0025
    def rd_(dx, dy, dz): return room(px + dx, py + dy, pz + dz)
    nx = (rd_(e, -e, -e) + rd_(-e, -e, e) + rd_(-e, e, -e) * -1 + rd_(e, e, e)) * 0
    # Tetrahedral normal, as in the shader.
    n1, n2, n3, n4 = rd_(e, -e, -e), rd_(-e, -e, e), rd_(-e, e, -e), rd_(e, e, e)
    nxv = e * n1 - e * n2 - e * n3 + e * n4
    nyv = -e * n1 - e * n2 + e * n3 + e * n4
    nzv = -e * n1 + e * n2 - e * n3 + e * n4
    ln = np.sqrt(nxv**2 + nyv**2 + nzv**2) + 1e-9
    nxv, nyv, nzv = nxv / ln, nyv / ln, nzv / ln

    skinx, skiny, skinz = px * 2.7, py * 2.7, pz * 2.7
    alloy_cast = grain3(skinx, skiny, skinz)
    dirt = grain3(px * 0.9, py * 0.9, pz * 0.16)
    ang_s = np.arctan2(py, px)
    seam = np.maximum(np.abs(np.mod(pz * 3.1, 1.0) - 0.5), np.abs(np.mod(ang_s * 5.7, 1.0) - 0.5))
    bolt = np.hypot(np.mod(pz * 3.1, 1.0) - 0.5, np.mod(ang_s * 5.7, 1.0) - 0.5)

    e = 0.02
    bx = (grain3(skinx + e, skiny, skinz) - alloy_cast) / e
    by = (grain3(skinx, skiny + e, skinz) - alloy_cast) / e
    bz = (grain3(skinx, skiny, skinz + e) - alloy_cast) / e
    detail = 1.0 - smoothstep(14.0, 30.0, t)
    dotbn = bx * nxv + by * nyv + bz * nzv
    relief = (0.06 * detail * (detail > 0.25))
    nxv, nyv, nzv = (nxv - (bx - nxv * dotbn) * relief, nyv - (by - nyv * dotbn) * relief,
                     nzv - (bz - nzv * dotbn) * relief)
    ln2 = np.sqrt(nxv**2 + nyv**2 + nzv**2) + 1e-9
    nxv, nyv, nzv = nxv / ln2, nyv / ln2, nzv / ln2

    sky = 0.5 + 0.5 * (nxv * 0.2571 + nyv * 0.8999 + nzv * -0.7714)
    alloy = (np.array([0.020, 0.026, 0.022]) * (1 - alloy_cast)[..., None]
             + np.array([0.048, 0.052, 0.040]) * alloy_cast[..., None])
    alloy *= (0.55 + 0.75 * (0.5 * (1 - detail) + dirt * detail))[..., None]
    alloy *= (1 - 0.55 * smoothstep(0.40, 0.49, seam))[..., None]
    alloy *= (1 - 0.35 * smoothstep(0.10, 0.05, bolt))[..., None]
    wall = alloy * (0.3 + 1.1 * sky)[..., None]

    light = lamp_colour(t) * lamp[..., None]

    dot = rdx * nxv + rdy * nyv + rdz * nzv
    rrx, rry, rrz = rdx - 2 * dot * nxv, rdy - 2 * dot * nyv, rdz - 2 * dot * nzv
    ox, oy, oz = px + nxv * 0.02, py + nyv * 0.02, pz + nzv * 0.02
    t2, hit2 = travel(ox, oy, oz, rrx, rry, rrz, STEPS // 3, np.full((H, W), 0.02))
    hit2 &= t < 26.0
    _, lamp2 = room(ox + rrx * t2, oy + rry * t2, oz + rrz * t2, True)
    light += lamp_colour(t + t2) * (lamp2 * hit2 * 0.85 * np.exp(-t2 * 0.08))[..., None]

    col = (wall + light) * (0.9 + 0.5 * drop) * np.exp(-t * 0.035)[..., None]
    return np.where(hit[..., None], col, 0.0), 0.8 + 0.6 * bands[0]

# ---------------- kaleidoscope ----------------
def prism(px, py, pz, sides, across, half):
    sector = TAU / sides
    a = np.mod(np.arctan2(py, px) + 0.5 * sector, sector) - 0.5 * sector
    return np.maximum(np.cos(a) * np.hypot(px, py) - across, np.abs(pz) - half)

def octa(px, py, pz, s):
    return (np.abs(px) + np.abs(py) + np.abs(pz) - s) * 0.57735

def seed(px, py, pz, which):
    if which < 0.5: return boxd(px, py, pz, girth * 1.5, arm * 0.22, girth * 1.5)
    if which < 1.5: return prism(px, py, pz, 3.0, girth * 2.0, arm * 0.22)
    if which < 2.5: return prism(px, py, pz, 6.0, girth * 1.8, arm * 0.24)
    return octa(px, py, pz, girth * 2.6)

SOLID_NOW = np.floor(min(3.99, (bite - 0.25) / 0.95 * 4))
SOLID_WAS = SOLID_NOW   # a still shows one section in a steady state, so the shape does not change

def filigree(px, py, pz):
    px, py = rot(px, py, pz * twist)
    px, py = wedge(px, py, folds); px = px - arm
    px, py = rot(px, py, pz * twist * 0.6)
    px, py = wedge(px, py, folds * 2.0); px = px - arm * 0.42
    px, py = np.abs(px) - arm * 0.16, np.abs(py) - arm * 0.16
    pz = np.mod(pz + 1.1 * ring, 2.2 * ring) - 1.1 * ring
    solid = seed(px, py, pz, SOLID_NOW)
    return np.maximum(solid, -cutout(px, py, pz, girth * 0.85 * bite))

def render_kaleidoscope():
    travel_z = travelled * 1.3
    rox = np.full((H, W), np.sin(beats * 0.11) * sway * 0.5)
    roy = np.full((H, W), np.cos(beats * 0.08) * sway * 0.5)
    n = np.sqrt(uvx**2 + uvy**2 + fov**2)
    rdx, rdy, rdz = uvx / n, uvy / n, np.full_like(uvx, fov) / n
    rdx, rdy = rot(rdx, rdy, orbit * 0.5 + np.sin(beats * 0.05) * sway * 0.2)
    t = dither * 0.3
    core = np.zeros((H, W)); haze = np.zeros((H, W))
    for i in range(STEPS):
        d = np.maximum(np.abs(filigree(rox + rdx * t, roy + rdy * t, travel_z + rdz * t)), 0.006)
        air = np.exp(-t * 0.11)
        core += (0.0022 / (0.0022 + d * d)) * air
        haze += (0.004 / (0.260 + d * d)) * air
        t = np.minimum(t + d * 0.6, 70.0)
    print('core p50 %.2f p90 %.2f max %.2f | haze p50 %.2f p90 %.2f max %.2f | t p50 %.1f' % (
        *np.percentile(core,[50,90,100]), *np.percentile(haze,[50,90,100]), np.percentile(t,50)))  # Debug output.
    fall = np.clip(np.hypot(uvx, uvy) * 1.20, 0, 1)[..., None]
    lit = [np.array([1.00, 0.76, 0.30]), np.array([1.00, 0.42, 0.60]),
           np.array([0.35, 1.00, 0.68]), np.array([0.45, 0.76, 1.00])][palette]
    dark = [np.array([0.09, 0.07, 0.16]), np.array([0.14, 0.05, 0.12]),
            np.array([0.04, 0.12, 0.11]), np.array([0.05, 0.08, 0.18])][palette]
    wash = lit * 0.9 * (1 - fall) + dark * fall
    level = 0.35 + 1.25 * (bands[0] * 0.35 + bands[1] * 0.45 + bands[2] * 0.20)
    strike = 0.85 + 0.5 * drop
    m = np.clip(bands[2] * 0.7, 0, 0.30)
    edge = lit * (1 - m) + np.array([1.0, 1.0, 1.0]) * m
    col = wash * (0.0025 + 0.004 * haze * level)[..., None] + edge * (core * 0.045 * level * strike)[..., None]
    return col, 0.20 + 0.35 * bands[1]

# ---------------- lattice ----------------
def render_lattice():
    size = 0.85 + ring * 0.15
    wire = girth * (0.35 + 0.55 * bands[1])
    bead = girth * (0.45 + 0.85 * bands[0]) * (1 + bite * 0.4)
    pull = 3.2 + 2.4 * bands[2]
    w = eased * 0.22
    tA, tB, tC = beats * 0.010, beats * 0.007, beats * 0.004
    n = np.sqrt(uvx**2 + uvy**2 + fov**2)
    rdx, rdy, rdz = uvx / n, uvy / n, np.full_like(uvx, fov) / n
    rdx, rdy = rot(rdx, rdy, orbit * 0.5)
    t = dither * 0.2
    col = np.zeros((H, W, 3))
    phases = [(0.15, 0.45, 0.75), (0.95, 0.30, 0.60), (0.40, 0.70, 0.15), (0.05, 0.35, 0.65)][palette]
    for i in range(STEPS):
        qx, qy, qz = rdx * t, rdy * t, -3.0 + rdz * t
        qw = np.full_like(qx, w)
        qx, qw = rot(qx, qw, tA); qy, qw = rot(qy, qw, tB); qz, qw = rot(qz, qw, tC)
        swell = np.clip(pull / np.maximum(qx**2 + qy**2 + qz**2 + qw**2, 0.6), 0.15, 6.0)
        qx, qy, qz, qw = qx * swell, qy * swell, qz * swell, qw * swell
        qx, qy, qz, qw = qx - w * 0.35, qy - w * 0.35, qz - w * 0.35, qw - w * 0.35
        cx, cy, cz, cw = qx / size, qy / size, qz / size, qw / size
        hx, hy, hz, hw = np.round(cx), np.round(cy), np.round(cz), np.round(cw)
        offx, offy, offz = (cx - hx) * size, (cy - hy) * size, (cz - hz) * size
        ax, ay, az, aw = [np.abs(c - h) * size for c, h in ((cx, hx), (cy, hy), (cz, hz), (cw, hw))]
        wires = np.minimum(np.minimum(np.sqrt(ay**2 + az**2 + aw**2), np.sqrt(ax**2 + az**2 + aw**2)),
                           np.minimum(np.sqrt(ax**2 + ay**2 + aw**2), np.sqrt(ax**2 + ay**2 + az**2))) - wire
        knot = np.sqrt(ax**2 + ay**2 + az**2 + aw**2) - bead
        d = np.minimum(wires, knot) / swell
        hsh = np.mod(np.sin(hx * 12.989 + hy * 78.233 + hz * 37.719) * 43758.5453, 1.0)
        olen = np.sqrt(offx**2 + offy**2 + offz**2) + 1e-5
        sheen = (offx * rdx + offy * rdy + offz * rdz) / olen
        shift = hsh * 0.35 + 0.12 * np.log2(np.maximum(swell, 0.05)) + 0.28 * sheen
        tint = np.clip(np.stack([0.5 + 0.72 * np.cos(TAU * (shift + p)) for p in phases], axis=-1), 0, 1)
        stride = np.maximum(np.abs(d), 0.02) * 0.75
        col += tint * (stride * (0.026 / (0.004 + d * d)) * (1.0 + 0.5 * drop) * np.exp(-t * 0.055))[..., None]
        t = t + stride
    level = 0.35 + 1.15 * (bands[0] * 0.4 + bands[1] * 0.3 + bands[2] * 0.3)
    return col * level * 1.05, 0.6 + 0.6 * bands[2]

col, bloom = {'tunnel': render_tunnel, 'kaleidoscope': render_kaleidoscope, 'lattice': render_lattice}[KIND]()
buf = col / (1.0 + col)
expand = lambda c: c / np.maximum(1.0 - c, 0.004)
src = expand(buf); halo = np.zeros_like(src)
for i in range(8):
    a = TAU * (i + 0.5) / 8
    for radius, weight in ((2.5, 0.65), (7.0, 0.35)):
        dx, dy = int(round(np.cos(a) * radius)), int(round(np.sin(a) * radius))
        halo += np.roll(np.roll(src, dy, 0), dx, 1) * weight
out = 1.0 - np.exp(-(src + halo * bloom * 0.045) * 0.95)
sat = {'tunnel': 1.40, 'kaleidoscope': 1.55, 'lattice': 1.35}[KIND]
out = np.clip((out @ np.array([0.2126, 0.7152, 0.0722]))[..., None] * (1 - sat) + out * sat, 0, 1)
qx2, qy2 = fx / W, fy / H
out *= (0.55 + 0.45 * np.power(np.clip(16 * qx2 * qy2 * (1 - qx2) * (1 - qy2), 0, None), 0.22))[..., None]
img = np.clip(out, 0, 1) ** (1 / 2.2)
if os.environ.get("HISTO"):
    lum = img @ np.array([0.2126, 0.7152, 0.0722])
    print("  tone: p05 %.3f p50 %.3f p95 %.3f p99 %.3f | black<0.05 %.1f%% | bright>0.80 %.1f%%" % (
        *np.percentile(lum, [5, 50, 95, 99]), (lum < 0.05).mean() * 100, (lum > 0.80).mean() * 100))
path = os.environ.get("OUT", f"RPM.Desktop/Assets/Viz/{KIND}.jpg")
Image.fromarray((img * 255).astype(np.uint8), "RGB").save(path, quality=92, subsampling=0)
print("wrote", path, "| folds", folds, "arm %.2f" % arm, "ring %.2f" % ring, "girth %.3f" % girth, "palette", palette)
