import sqlite3
import time
import json
import sys

PASS = 0
FAIL = 0

def test(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} - {detail}")

print("="*60)
print("PRUEBA COMPLETA - VIERNES AI")
print("="*60)

# ============================================
print("\n--- F1: LOGGER DE ACTIVIDAD ---")
try:
    conn = sqlite3.connect("events.db")
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    test("Tabla events existe", "events" in tables)

    count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    test("Eventos capturados", count > 0, f"Tiene {count} eventos")

    if count > 0:
        apps = conn.execute("SELECT DISTINCT app_name FROM events WHERE app_name IS NOT NULL AND app_name != ''").fetchall()
        test("Apps detectadas", len(apps) > 0, f"Apps: {[a[0][:20] for a in apps[:5]]}")

        types = conn.execute("SELECT DISTINCT event_type FROM events").fetchall()
        test("Tipos de eventos variados", len(types) > 1, f"Tipos: {[t[0] for t in types]}")

        dur = conn.execute("SELECT SUM(duration) FROM events WHERE duration IS NOT NULL").fetchone()[0]
        test("Duracion registrada", (dur or 0) > 0, f"Total: {dur:.1f}s")

        latest = conn.execute("SELECT timestamp FROM events ORDER BY timestamp DESC LIMIT 1").fetchone()[0]
        print(f"  INFO: Ultimo evento: {latest[:19]}")
    conn.close()
except Exception as e:
    test("Logger F1", False, str(e))

# ============================================
print("\n--- F2: MEMORIA SEMANTICA (ChromaDB) ---")
try:
    import chromadb
    client = chromadb.PersistentClient(path="chroma_db")
    cols = [c.name for c in client.list_collections()]
    test("ChromaDB collection existe", "viernes_sessions" in cols, f"Colecciones: {cols}")

    if "viernes_sessions" in cols:
        col = client.get_collection("viernes_sessions")
        count = col.count()
        test("Sesiones indexadas", count > 0, f"Sesiones: {count}")

        if count > 0:
            data = col.get(limit=1)
            if data and data.get("metadatas"):
                meta = data["metadatas"][0]
                test("Metadata de sesion completa", 
                     all(k in meta for k in ["start_ts", "end_ts", "top_apps"]),
                     f"Meta keys: {list(meta.keys())}")
    print("  INFO: ChromaDB OK")
except Exception as e:
    test("ChromaDB F2", False, str(e))

# ============================================
print("\n--- F2b: BUSQUEDA SEMANTICA ---")
try:
    from semantic_query import load_collection, search_sessions
    col = load_collection("chroma_db", "viernes_sessions", "all-MiniLM-L6-v2")
    matches = search_sessions(col, "que estaba haciendo", 3)
    test("Busqueda devuelve resultados", len(matches) > 0, f"Resultados: {len(matches)}")
    if matches:
        test("Resultados tienen metadata", 
             all(m.get("metadata") for m in matches),
             f"Primer match: {matches[0].get('id')}")
except Exception as e:
    test("Busqueda semantica", False, str(e))

# ============================================
print("\n--- F3: CONTROL DEL OS ---")
try:
    from os_controller import OSController
    from permissions import load_permissions
    ctrl = OSController(permissions=load_permissions())

    r = ctrl.execute_action("open_app", {"app": "notepad"})
    test("Abrir app notepad", r.get("status") == "ok", str(r))

    r = ctrl.execute_action("open_url", {"url": "https://google.com"})
    test("Abrir URL google", r.get("status") == "ok", str(r))

    r = ctrl.execute_action("type_text", {"text": "Hola desde Viernes"})
    test("Escribir texto", r.get("status") == "ok", str(r))

    r = ctrl.execute_action("screenshot", {"path": r"C:\Users\USUARIO\Documents\test_viernes.png"})
    test("Tomar screenshot", r.get("status") == "ok", str(r))
except Exception as e:
    test("Control OS F3", False, str(e))

# ============================================
print("\n--- F3b: FRIDAY EXECUTOR (accion desde texto) ---")
try:
    from action_bridge import plan_action_from_text
    plan = plan_action_from_text(
        "abre el bloc de notas",
        "Sin contexto relevante.",
        model="llama3.2:3b"
    )
    test("Planifica accion desde texto", 
         isinstance(plan, dict) and "action" in plan,
         f"Plan: {json.dumps(plan, indent=2)[:200]}")
except Exception as e:
    test("Action Bridge F3b", False, str(e))

# ============================================
print("\n--- F4: DETECCION DE PATRONES ---")
try:
    from phase4_patterns import fetch_event_tokens
    conn2 = sqlite3.connect("events.db")
    conn2.row_factory = sqlite3.Row
    tokens = fetch_event_tokens(conn2, limit=500)
    test("Tokens de eventos disponibles", len(tokens) > 0, f"Tokens: {len(tokens)}")

    if len(tokens) > 0:
        test("Tokens son EventToken", hasattr(tokens[0], "token"), f"Primer token: {tokens[0].token}")

        from phase4_patterns import detect_frequent_sequences
        candidates = detect_frequent_sequences(tokens, min_occurrences=2)
        test("Secuencias detectadas", len(candidates) > 0, f"Candidatos: {len(candidates)}")
        if candidates:
            print(f"  INFO: Primer patron: {candidates[0].sequence[:3]}... ({candidates[0].occurrences}x)")
    conn2.close()
except Exception as e:
    test("Patrones F4", False, str(e))

# ============================================
print("\n--- F5: VOZ (TTS) ---")
try:
    from voice import speak, load_whisper_model
    test("Modulo voice importa OK", True)
    
    whisper_model = load_whisper_model("small")
    test("Whisper carga modelo", whisper_model is not None)
except Exception as e:
    test("Voice F5", False, str(e))

# ============================================
print("\n--- F5: SYSTRAY ---")
try:
    import pystray
    from PIL import Image
    test("Pystray importa OK", True)
    test("Pillow importa OK", True)
except Exception as e:
    test("Systray F5", False, str(e))

# ============================================
print("\n--- F5: PERMISOS Y SEGURIDAD ---")
try:
    from permissions import load_permissions
    perms = load_permissions()
    test("Permissions carga OK", perms is not None)
    
    from permissions import PermissionsConfig
    test("Permisos permiten notepad", perms.is_app_allowed("notepad"), "notepad en whitelist")
    test("Permisos bloquean app desconocida", not perms.is_app_allowed("hacker_tool"), "no deberia estar")
    test("Permisos permiten Documents", perms.is_path_allowed(r"C:\Users\USUARIO\Documents"))
except Exception as e:
    test("Permisos", False, str(e))

# ============================================
print("\n--- OLLAMA CLIENT ---")
try:
    from ollama_client import generate_ollama
    test("Ollama client importa OK", True)
except Exception as e:
    test("Ollama client", False, str(e))

# ============================================
print("\n--- MODEL CACHE ---")
try:
    from model_cache import get_embedding_function, clear_cache
    fn = get_embedding_function("all-MiniLM-L6-v2")
    test("Cache de embeddings funciona", fn is not None)
    clear_cache()
    test("Cache se limpia OK", True)
except Exception as e:
    test("Model cache", False, str(e))

# ============================================
print("\n" + "="*60)
print(f"RESULTADO FINAL: {PASS} PASARON, {FAIL} FALLARON de {PASS+FAIL}")
print("="*60)
