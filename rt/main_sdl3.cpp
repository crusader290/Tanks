// SDL3 front-end for the statically recompiled Flash game (tools/recomp/gen.py -> gen/*.cpp).
// Logic: fixed ticks at the SWF frame rate. Rendering: the display list is painted in software (PlutoVG, the same
// painter as BitmapData.draw) into a window-resolution buffer and uploaded to an SDL3 streaming texture.
// Assets (shapes, bitmaps, fonts, sounds) are read at runtime from the user's own SWF; none are embedded.
#include "display.h"
#include "raster.h"
#include "platform.h"
#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <algorithm>
#include <cmath>

namespace fl {
void initGlobals();
void runIntervals();
void audioInit(bool device);
void audioShutdown();
extern bool g_mouseHidden;
}
using namespace fl;

// SDL keycode -> Flash Key.getCode() (virtual key codes, as Flash Player on Windows)
static int flashKeyCode(SDL_Keycode k) {
    if (k >= SDLK_A && k <= SDLK_Z) return 'A' + (int)(k - SDLK_A);
    if (k >= SDLK_0 && k <= SDLK_9) return '0' + (int)(k - SDLK_0);
    if (k >= SDLK_F1 && k <= SDLK_F12) return 112 + (int)(k - SDLK_F1);
    if (k >= SDLK_KP_1 && k <= SDLK_KP_9) return 97 + (int)(k - SDLK_KP_1);
    switch (k) {
        case SDLK_KP_0: return 96;
        case SDLK_BACKSPACE: return 8; case SDLK_TAB: return 9; case SDLK_RETURN: case SDLK_KP_ENTER: return 13;
        case SDLK_LSHIFT: case SDLK_RSHIFT: return 16; case SDLK_LCTRL: case SDLK_RCTRL: return 17;
        case SDLK_LALT: case SDLK_RALT: return 18; case SDLK_PAUSE: return 19; case SDLK_CAPSLOCK: return 20;
        case SDLK_ESCAPE: return 27; case SDLK_SPACE: return 32; case SDLK_PAGEUP: return 33; case SDLK_PAGEDOWN: return 34;
        case SDLK_END: return 35; case SDLK_HOME: return 36; case SDLK_LEFT: return 37; case SDLK_UP: return 38;
        case SDLK_RIGHT: return 39; case SDLK_DOWN: return 40; case SDLK_INSERT: return 45; case SDLK_DELETE: return 46;
        case SDLK_KP_MULTIPLY: return 106; case SDLK_KP_PLUS: return 107; case SDLK_KP_MINUS: return 109;
        case SDLK_KP_PERIOD: return 110; case SDLK_KP_DIVIDE: return 111;
        case SDLK_SEMICOLON: return 186; case SDLK_EQUALS: return 187; case SDLK_COMMA: return 188; case SDLK_MINUS: return 189;
        case SDLK_PERIOD: return 190; case SDLK_SLASH: return 191; case SDLK_GRAVE: return 192; case SDLK_LEFTBRACKET: return 219;
        case SDLK_BACKSLASH: return 220; case SDLK_RIGHTBRACKET: return 221; case SDLK_APOSTROPHE: return 222;
        default: return 0;
    }
}
// Key.getAscii() for a key press (printable keys; the text itself comes from SDL text input events)
static int flashAscii(SDL_Keycode k, SDL_Keymod mod, int code) {
    if (k >= 32 && k < 127) {
        int c = (int)k;
        if ((mod & SDL_KMOD_SHIFT) && c >= 'a' && c <= 'z') c -= 32;
        return c;
    }
    switch (code) { case 8: return 8; case 9: return 9; case 13: return 13; case 27: return 27; case 46: return 127; default: return 0; }
}

static std::string findSwf(int argc, char** argv) {
    if (argc > 1) return argv[1];
    std::vector<std::string> cands;
    if (const char* base = SDL_GetBasePath()) { cands.push_back(std::string(base) + "tanks.swf"); cands.push_back(std::string(base) + "../tanks.swf"); }
    cands.push_back("tanks.swf");
    for (auto& c : cands) if (FILE* f = fopen(c.c_str(), "rb")) { fclose(f); return c; }
    return "tanks.swf";
}

struct View { float x = 0, y = 0, w = 1, h = 1; int pw = 1, ph = 1; };   // letterboxed stage rectangle in pixels
static View computeView(SDL_Window* win) {
    View v; int ww = 1, wh = 1; SDL_GetWindowSizeInPixels(win, &ww, &wh);
    double sx = (double)ww / g_movie.width, sy = (double)wh / g_movie.height, s = std::min(sx, sy);
    v.pw = std::max(1, (int)std::lround(g_movie.width * s)); v.ph = std::max(1, (int)std::lround(g_movie.height * s));
    v.x = (float)((ww - v.pw) / 2); v.y = (float)((wh - v.ph) / 2); v.w = (float)v.pw; v.h = (float)v.ph;
    return v;
}
// window (logical) coordinates -> stage coordinates
static void toStage(SDL_Window* win, const View& v, float x, float y, double& sx, double& sy) {
    int lw = 1, lh = 1, pw = 1, ph = 1; SDL_GetWindowSize(win, &lw, &lh); SDL_GetWindowSizeInPixels(win, &pw, &ph);
    double dpx = (double)pw / lw, dpy = (double)ph / lh;
    sx = (x * dpx - v.x) / v.w * g_movie.width; sy = (y * dpy - v.y) / v.h * g_movie.height;
}

// paints the display list into bd (w x h pixels, the whole stage)
static void renderStage(BitmapData* bd, int w, int h) {
    if (bd->w != w || bd->h != h) { bd->w = w; bd->h = h; bd->px.assign((size_t)w * h, 0); }
    std::fill(bd->px.begin(), bd->px.end(), g_movie.bgColor | 0xff000000u);
    bd->lazy = false; bd->version++;
    Mat m; m.a = (double)w / g_movie.width; m.d = (double)h / g_movie.height;
    bitmapDraw(bd, (Object*)vm.root, m, nullptr);
}

// ---- headless test mode: tanks --test FRAMES [--shot out.bmp] [--scale S] [--click F:X:Y]... [--key F:CODE]...
//      [--shots-every N] [--type F:TEXT]: runs FRAMES ticks without a window and writes the last frame (or every Nth)
struct TestEv { int frame; int kind; double x, y; int code; std::string text; };   // kind 0 click, 1 key, 2 text
static bool saveBmp(BitmapData* bd, const std::string& path) {
    SDL_Surface* s = SDL_CreateSurfaceFrom(bd->w, bd->h, SDL_PIXELFORMAT_ARGB8888, bd->px.data(), bd->w * 4);
    if (!s) return false;
    bool ok = SDL_SaveBMP(s, path.c_str());
    SDL_DestroySurface(s);
    return ok;
}
// --dump F:PATH: prints the object at a target path ("_root.tank_2") with its own properties (debugging)
static void dumpObject(int frame, const std::string& path) {
    Act a{vm.globalScope, VUNDEF, vm.root, nullptr};
    Value v = resolveTargetPath(a, Value(mkstr(path)));
    if (!v.isObj()) { logf("[dump] frame %d %s: (not found)\n", frame, path.c_str()); return; }
    Object* o = v.o;
    std::string head = "[dump] frame " + std::to_string(frame) + " " + path;
    if (o->isDisplay() && ((DisplayObject*)o)->kind == OK_CLIP) {
        MovieClip* c = (MovieClip*)o;
        head += " clip#" + std::to_string(c->charId) + " frame " + std::to_string(c->cur) + "/" + std::to_string(c->def ? c->def->nframes : 0) +
                (c->playing ? " playing" : " stopped") + " kids=" + std::to_string(c->kids.size());
    }
    logf("%s\n", head.c_str());
    if (o->isDisplay() && ((DisplayObject*)o)->kind == OK_CLIP)
        for (auto* k : ((MovieClip*)o)->kids) {
            if (!k->name || k->name->s.compare(0, 8, "instance") == 0) continue;
            std::string extra = k->kind == OK_CLIP ? " frame " + std::to_string(((MovieClip*)k)->cur) + (((MovieClip*)k)->playing ? " playing" : " stopped") : "";
            logf("    child %s (char %d, depth %d)%s%s\n", k->name->s.c_str(), k->charId, k->depth, extra.c_str(), k->visible ? "" : " hidden");
        }
    for (auto& p : o->props.v) {
        std::string val;
        if (p.v.isObj()) val = p.v.o->isDisplay() ? "[clip " + toStr(p.v)->s + "]" : (p.v.o->kind == OK_FUNCTION ? "[function]" : "[object]");
        else val = toStr(p.v)->s;
        if (val.size() > 60) val = val.substr(0, 60) + "...";
        logf("    %s = %s%s\n", p.k->s.c_str(), val.c_str(), p.v.isUndef() ? " (undefined)" : "");
    }
}

static int runTest(int frames, const std::string& shot, double scale, int every, std::vector<TestEv> evs) {
    audioInit(false);
    playerInit();
    BitmapData* stage = gcNew<BitmapData>(); gcPin(stage); stage->transparent = false;
    int w = (int)std::lround(g_movie.width * scale), h = (int)std::lround(g_movie.height * scale);
    const double tickMs = 1000.0 / (g_movie.frameRate > 0 ? g_movie.frameRate : 25.0);
    for (int f = 1; f <= frames; f++) {
        for (auto& e : evs) if (e.frame == f) {
            if (e.kind == 0) { mouseEvent(e.x, e.y, 0); mouseEvent(e.x, e.y, 1); mouseEvent(e.x, e.y, 2); logf("[test] frame %d click %.0f,%.0f\n", f, e.x, e.y); }
            else if (e.kind == 1) { keyEvent(e.code, e.code < 128 ? e.code : 0, true); logf("[test] frame %d key %d down\n", f, e.code); }
            else if (e.kind == 3) { keyEvent(e.code, 0, false); logf("[test] frame %d key %d up\n", f, e.code); }
            else if (e.kind == 4) dumpObject(f, e.text);
            else { textInputEvent(e.text.c_str()); logf("[test] frame %d text '%s'\n", f, e.text.c_str()); }
        }
        g_player.timeMs = f * tickMs;
        runFrame(); runIntervals(); gcCollect();
        if (every > 0 && f % every == 0 && !shot.empty()) {
            renderStage(stage, w, h);
            std::string p = shot; size_t dot = p.rfind('.');
            char suf[32]; snprintf(suf, sizeof suf, "_%05d", f);
            p.insert(dot == std::string::npos ? p.size() : dot, suf);
            saveBmp(stage, p);
        }
    }
    if (!shot.empty()) {
        renderStage(stage, w, h);
        if (!saveBmp(stage, shot)) { logf("cannot write %s: %s\n", shot.c_str(), SDL_GetError()); return 1; }
        logf("[test] %d frames, wrote %s (%dx%d)\n", frames, shot.c_str(), w, h);
    }
    return 0;
}

int main(int argc, char** argv) {
    int testFrames = 0, every = 0, winSizeW = 0, winSizeH = 0; double scale = 1; std::string shot; std::vector<TestEv> evs;
    std::vector<char*> rest = {argv[0]};
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        auto next = [&]() -> std::string { return i + 1 < argc ? argv[++i] : ""; };
        if (a == "--test") testFrames = atoi(next().c_str());
        else if (a == "--shot") shot = next();
        else if (a == "--size") sscanf(next().c_str(), "%dx%d", &winSizeW, &winSizeH);
        else if (a == "--scale") scale = atof(next().c_str());
        else if (a == "--shots-every") every = atoi(next().c_str());
        else if (a == "--click") { TestEv e{}; e.kind = 0; sscanf(next().c_str(), "%d:%lf:%lf", &e.frame, &e.x, &e.y); evs.push_back(e); }
        else if (a == "--key") {   // F:CODE[:HOLD]: pressed at frame F, released HOLD frames later (default 3)
            TestEv e{}; e.kind = 1; int hold = 3;
            sscanf(next().c_str(), "%d:%d:%d", &e.frame, &e.code, &hold);
            evs.push_back(e); TestEv u = e; u.kind = 3; u.frame = e.frame + std::max(1, hold); evs.push_back(u);
        }
        else if (a == "--dump") { TestEv e{}; e.kind = 4; std::string v = next(); size_t c = v.find(':'); e.frame = atoi(v.c_str()); e.text = c == std::string::npos ? "_root" : v.substr(c + 1); evs.push_back(e); }
        else if (a == "--type") { TestEv e{}; e.kind = 2; std::string v = next(); size_t c = v.find(':'); e.frame = atoi(v.c_str()); e.text = c == std::string::npos ? "" : v.substr(c + 1); evs.push_back(e); }
        else rest.push_back(argv[i]);
    }
    argc = (int)rest.size(); argv = rest.data();
    if (!SDL_Init(testFrames ? 0 : (SDL_INIT_VIDEO | SDL_INIT_AUDIO))) { fprintf(stderr, "SDL_Init: %s\n", SDL_GetError()); return 1; }
    platformInitLimits();
    initGlobals();
    std::string path = findSwf(argc, argv), err;
    if (testFrames) {
        if (!g_movie.load(path, err)) { fprintf(stderr, "cannot load %s: %s\n", path.c_str(), err.c_str()); return 1; }
        int r = runTest(testFrames, shot, scale, every, evs);
        SDL_Quit();
        return r;
    }
    if (!g_movie.load(path, err)) {
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "Tanks", ("Cannot load " + path + ": " + err).c_str(), nullptr);
        return 1;
    }
    logf("loaded %s: SWF%d, %dx%d @ %.1f fps\n", path.c_str(), g_movie.version, g_movie.width, g_movie.height, g_movie.frameRate);

    // window size: --size WxH, else the largest half-step multiple of the stage (550x400: 1x, 1.5x, 2x, 2.5x...)
    // that fits 90% of the primary display's usable area (taskbar and title bar excluded)
    int winW = winSizeW, winH = winSizeH;
    if (winW <= 0 || winH <= 0) {
        double sc = 1;
        SDL_Rect ub;
        if (SDL_GetDisplayUsableBounds(SDL_GetPrimaryDisplay(), &ub) && ub.w > 0 && ub.h > 0) {
            double fit = std::min(ub.w * 0.9 / g_movie.width, ub.h * 0.9 / g_movie.height);
            sc = std::max(1.0, std::floor(fit * 2) / 2);
            logf("display usable area %dx%d: window at %.1fx the stage\n", ub.w, ub.h, sc);
        }
        winW = (int)std::lround(g_movie.width * sc); winH = (int)std::lround(g_movie.height * sc);
    }
    SDL_Window* win = SDL_CreateWindow("Tanks", winW, winH, SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY);
    if (!win) { fprintf(stderr, "SDL_CreateWindow: %s\n", SDL_GetError()); return 1; }
    float aspect = (float)g_movie.width / g_movie.height;   // resizing keeps the stage's 11:8 shape (no letterbox bars)
    SDL_SetWindowAspectRatio(win, aspect, aspect);
    SDL_SetWindowMinimumSize(win, g_movie.width / 2, g_movie.height / 2);
    SDL_Renderer* ren = SDL_CreateRenderer(win, nullptr);
    if (!ren) { fprintf(stderr, "SDL_CreateRenderer: %s\n", SDL_GetError()); return 1; }
    SDL_SetRenderVSync(ren, 1);
    SDL_StartTextInput(win);

    audioInit(true);
    playerInit();

    BitmapData* stage = gcNew<BitmapData>(); gcPin(stage);
    stage->transparent = false;
    SDL_Texture* tex = nullptr; int texW = 0, texH = 0;

    const double tickMs = 1000.0 / (g_movie.frameRate > 0 ? g_movie.frameRate : 25.0);
    const Uint64 freq = SDL_GetPerformanceFrequency(), start = SDL_GetPerformanceCounter();
    double nextTick = 0; bool running = true; bool hidden = false;
    View view = computeView(win);

    while (running && !g_player.quit) {
        SDL_Event ev;
        while (SDL_PollEvent(&ev)) {
            switch (ev.type) {
                case SDL_EVENT_QUIT: running = false; break;
                case SDL_EVENT_KEY_DOWN: case SDL_EVENT_KEY_UP: {
                    bool down = ev.type == SDL_EVENT_KEY_DOWN;
                    if (down && ev.key.key == SDLK_F11) { bool fs = SDL_GetWindowFlags(win) & SDL_WINDOW_FULLSCREEN; SDL_SetWindowFullscreen(win, !fs); break; }
                    int code = flashKeyCode(ev.key.key); if (!code) break;
                    if (down && ev.key.repeat && code != 37 && code != 38 && code != 39 && code != 40 && code != 8) break;
                    keyEvent(code, down ? flashAscii(ev.key.key, ev.key.mod, code) : 0, down);
                    break;
                }
                case SDL_EVENT_TEXT_INPUT: textInputEvent(ev.text.text); break;
                case SDL_EVENT_MOUSE_MOTION: { double x, y; toStage(win, view, ev.motion.x, ev.motion.y, x, y); mouseEvent(x, y, 0); break; }
                case SDL_EVENT_MOUSE_BUTTON_DOWN: case SDL_EVENT_MOUSE_BUTTON_UP: {
                    if (ev.button.button != SDL_BUTTON_LEFT) break;
                    double x, y; toStage(win, view, ev.button.x, ev.button.y, x, y);
                    mouseEvent(x, y, ev.type == SDL_EVENT_MOUSE_BUTTON_DOWN ? 1 : 2);
                    break;
                }
                case SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED: case SDL_EVENT_WINDOW_RESIZED: view = computeView(win); break;
                default: break;
            }
        }
        if (g_mouseHidden != hidden) { hidden = g_mouseHidden; if (hidden) SDL_HideCursor(); else SDL_ShowCursor(); }

        // logic: fixed ticks at the SWF frame rate (at most a few per loop iteration after a stall)
        double now = (SDL_GetPerformanceCounter() - start) * 1000.0 / freq;
        int steps = 0;
        while (now >= nextTick && steps < 4) {
            g_player.timeMs = now;
            runFrame(); runIntervals();
            gcCollect();
            nextTick += tickMs; steps++;
        }
        if (now - nextTick > tickMs * 4) nextTick = now;   // too far behind: drop ticks rather than spiral

        // render: the whole display list at window resolution
        if (!tex || texW != view.pw || texH != view.ph) {
            if (tex) SDL_DestroyTexture(tex);
            texW = view.pw; texH = view.ph;
            tex = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, texW, texH);
            SDL_SetTextureScaleMode(tex, SDL_SCALEMODE_NEAREST);
        }
        renderStage(stage, texW, texH);
        SDL_UpdateTexture(tex, nullptr, stage->px.data(), texW * 4);
        SDL_SetRenderDrawColor(ren, 0, 0, 0, 255);
        SDL_RenderClear(ren);
        SDL_FRect dst{view.x, view.y, view.w, view.h};
        SDL_RenderTexture(ren, tex, nullptr, &dst);
        SDL_RenderPresent(ren);
    }
    audioShutdown();
    SDL_DestroyTexture(tex);
    SDL_DestroyRenderer(ren);
    SDL_DestroyWindow(win);
    SDL_Quit();
    return 0;
}
