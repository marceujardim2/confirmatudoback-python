import os
import time
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

load_dotenv()

app = Flask(__name__)

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://confirmatudo.lovable.app")
IFOOD_URL = os.getenv("IFOOD_URL", "https://confirmacao-entrega-propria.ifood.com.br/numero-pedido")
NINENINE_URL = os.getenv("NINENINE_URL", "https://food-b-h5.99app.com/pt-BR/v2/confirmation-entrega/locator")
PORT = int(os.getenv("PORT", 10000))
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{PORT}")

# ---------- Helpers genéricos para preencher inputs ----------
def fill_digits_inputs(page: Page, container_selector: str, digits: str, single_digit_input_selector: str = "input"):
    """
    Preenche inputs individuais (cada dígito num input com maxlength=1).
    container_selector: seletor do container que tem vários inputs.
    digits: string com dígitos a inserir.
    """
    inputs = page.query_selector_all(f"{container_selector} {single_digit_input_selector}")
    if not inputs:
        return False
    if len(digits) != len(inputs) and len(inputs) >= len(digits):
        # aceita se houver inputs >= quantidade de dígitos
        for i, ch in enumerate(digits):
            inputs[i].fill(ch)
        return True
    if len(digits) == len(inputs):
        for i, ch in enumerate(digits):
            inputs[i].fill(ch)
        return True
    # fallback: if counts mismatch, try filling as much
    for i, ch in enumerate(digits[:len(inputs)]):
        inputs[i].fill(ch)
    return True

def fill_single_input(page: Page, selector: str, value: str):
    el = page.query_selector(selector)
    if not el:
        return False
    try:
        el.fill(value)
        return True
    except Exception:
        # às vezes precisa set_value via eval
        page.eval_on_selector(selector, "el => el.value = arguments[0]", value)
        return True

def try_click(page: Page, selector: str):
    btn = page.query_selector(selector)
    if not btn:
        return False
    try:
        btn.click()
        return True
    except Exception:
        try:
            page.evaluate("(sel)=>document.querySelector(sel).click()", selector)
            return True
        except Exception:
            return False

# ---------- Estratégias específicas por plataforma ----------
def preencher_localizador_ifood(page: Page, localizador: str):
    # Tenta várias estratégias para inserir o localizador (8 dígitos)
    # 1) selector por nome (quando existe input único)
    candidates_single = [
        'input[name="locatorNumber"]',
        'input[name="orderLocator"]',
        'input[type="tel"][maxlength="8"]',
        'input[type="text"][maxlength="8"]',
        'input[aria-label*="locator"]',
        'input[aria-label*="Localizador"]'
    ]
    for sel in candidates_single:
        el = page.query_selector(sel)
        if el:
            try:
                el.fill(localizador)
                return True
            except:
                pass

    # 2) inputs individuais por dígito (containers)
    candidates_containers = [
        '.OptInput__container',            # exemplo de classe da screenshot
        '.verification-code-input',        # outro
        '.delivery-code-wrapper',
        '.verification-wrapper',
        'div[class*="OptInput"]',
        'div[class*="verification"]',
    ]
    for cont in candidates_containers:
        if page.query_selector(cont):
            ok = fill_digits_inputs(page, cont, localizador, single_digit_input_selector='input')
            if ok:
                return True

    # 3) fallback: escrever via JS em algum campo visível
    visible_input = page.query_selector("input:visible")
    if visible_input:
        visible_input.fill(localizador)
        return True

    return False

def preencher_codigo_ifood(page: Page, codigo: str):
    # tenta preencher código de 4 dígitos
    candidates_single = [
        'input[name="code"]',
        'input[type="tel"][maxlength="4"]',
        'input[type="text"][maxlength="4"]',
        'input[aria-label*="code"]',
        'input[aria-label*="código"]'
    ]
    for sel in candidates_single:
        el = page.query_selector(sel)
        if el:
            try:
                el.fill(codigo)
                return True
            except:
                pass

    candidates_containers = [
        '.OptInput__container',
        '.verification-code-input',
        '.delivery-code-wrapper',
        '.verification-wrapper',
        'div[class*="OptInput"]'
    ]
    for cont in candidates_containers:
        if page.query_selector(cont):
            ok = fill_digits_inputs(page, cont, codigo, single_digit_input_selector='input')
            if ok:
                return True

    # fallback
    visible_input = page.query_selector("input:visible")
    if visible_input:
        visible_input.fill(codigo)
        return True

    return False

def is_confirmation_page_ifood(page: Page):
    # detecta texto de sucesso na página
    # tenta encontrar elementos que contenham "Agradecemos pela entrega" ou similares
    texts = ["Agradecemos pela entrega", "pedido foi confirmado", "Entrega confirmada", "Obrigado pela entrega"]
    content = page.content().lower()
    for t in texts:
        if t.lower() in content:
            return True
    # também verifica se existe elemento com classe success-text
    if page.query_selector("div.success-text") or page.query_selector(".completed-wrapper"):
        return True
    return False

def is_stuck_on_locator_page_ifood(page: Page):
    # se o botão continuar estiver disabled ou a página ainda tem os inputs de localizador
    try:
        cont_btn = page.query_selector("button[data-testid='continue-button'], button[type='submit'], button:has-text('Continuar')")
        if cont_btn:
            disabled = cont_btn.get_attribute("disabled")
            if disabled:
                return True
    except:
        pass
    # se ainda houver muitos inputs para localizador
    if page.query_selector('input[name="locatorNumber"]') or page.query_selector('.OptInput__container'):
        # mas não necessariamente falha — devolve True só se necessário
        return True
    return False

# ---------- Fluxos por plataforma ----------
def confirmar_ifood(playwright, localizador: str, codigo: str, timeout_ms=30000):
    browser = playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
    page = browser.new_page()
    page.set_default_timeout(timeout_ms)
    try:
        page.goto(IFOOD_URL, wait_until="networkidle")
    except PWTimeout:
        # tenta continuar mesmo com timeout
        pass

    # preencher localizador
    filled_locator = False
    try:
        # espera por algo parecido com os inputs
        page.wait_for_timeout(800)  # pequena espera sua UI carregar
        filled_locator = preencher_localizador_ifood(page, localizador)
    except Exception:
        filled_locator = preencher_localizador_ifood(page, localizador)

    # clicar em continuar
    # tenta clicar no botão continuar/verificar
    buttons = [
        "button[type='submit']",
        "button:has-text('Continuar')",
        "button:has-text('Verificar e continuar')",
        "button[data-testid='continue-button']",
        ".action-button button",
        "button"
    ]
    for b in buttons:
        if try_click(page, b):
            break
    # aguarda navegação/ carregamento
    page.wait_for_timeout(1500)

    # se não avançou (localizador inválido), detecta e retorna false
    if is_stuck_on_locator_page_ifood(page) and not preencher_codigo_ifood(page, codigo):
        # localizador possivelmente inválido
        browser.close()
        return {"success": False, "reason": "localizador_invalido"}

    # agora preencher o código quando a UI pedir (pode ter nova página ou mesmo modal)
    # espera um pouco pela área do código
    page.wait_for_timeout(1200)
    filled_code = preencher_codigo_ifood(page, codigo)
    if not filled_code:
        # talvez precise aguardar carregamento do campo do código
        try:
            page.wait_for_selector('input[name="code"]', timeout=3000)
            filled_code = preencher_codigo_ifood(page, codigo)
        except Exception:
            filled_code = False

    if filled_code:
        # clicar botão confirmar / enviar
        for b in ["button[type='submit']", "button:has-text('Concluir a entrega')", "button:has-text('Confirmar')", "button:has-text('Continuar')", "button[data-testid='continue-button']"]:
            if try_click(page, b):
                break
        page.wait_for_timeout(1500)

    # verifica sucesso
    success = is_confirmation_page_ifood(page)
    browser.close()
    if success:
        return {"success": True, "message": "Entrega confirmada no iFood!"}
    else:
        # se não conseguiu e já tentou preencher código, sinalizamos código inválido
        return {"success": False, "reason": "codigo_invalido" if filled_code else "erro_desconhecido"}

def preencher_localizador_99(page: Page, localizador: str):
    # reusa estratégias parecidas para 99
    candidates_single = [
        'input[name="locatorNumber"]',
        'input[data-testid="locator-input"]',
        'input[type="tel"][maxlength="8"]',
        'input[type="text"][maxlength="8"]',
        'input[aria-label*="locator"]',
    ]
    for sel in candidates_single:
        if page.query_selector(sel):
            try:
                page.fill(sel, localizador)
                return True
            except:
                pass

    candidates_containers = ['.verification-code-input', '.OptInput__container', 'div[class*="OptInput"]', '.delivery-code-wrapper']
    for cont in candidates_containers:
        if page.query_selector(cont):
            if fill_digits_inputs(page, cont, localizador, single_digit_input_selector='input'):
                return True
    return False

def preencher_codigo_99(page: Page, codigo: str):
    candidates_single = [
        'input[name="code"]',
        'input[data-testid="handshake-code-input-0"]',
        'input[type="tel"][maxlength="4"]',
    ]
    for sel in candidates_single:
        if page.query_selector(sel):
            try:
                page.fill(sel, codigo)
                return True
            except:
                pass
    candidates_containers = ['.OptInput__container', '.verification-code-input', 'div[class*="OptInput"]']
    for cont in candidates_containers:
        if page.query_selector(cont):
            if fill_digits_inputs(page, cont, codigo, single_digit_input_selector='input'):
                return True
    return False

def is_confirmation_page_99(page: Page):
    texts = ["Agradecemos pela entrega", "pedido foi confirmado", "Entrega confirmada", "Obrigado pela entrega"]
    content = page.content().lower()
    for t in texts:
        if t.lower() in content:
            return True
    if page.query_selector(".completed-wrapper") or page.query_selector(".success-text"):
        return True
    return False

def confirmar_99(playwright, localizador: str, codigo: str, timeout_ms=30000):
    browser = playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
    page = browser.new_page()
    page.set_default_timeout(timeout_ms)
    try:
        page.goto(NINENINE_URL, wait_until="networkidle")
    except PWTimeout:
        pass

    page.wait_for_timeout(800)
    filled_locator = preencher_localizador_99(page, localizador)
    # clicar continuar
    for b in ["button[type='submit']", "button:has-text('Continuar')", "button"]:
        if try_click(page, b):
            break
    page.wait_for_timeout(1200)

    # se não avançou
    if page.query_selector('.OptInput__container') and not preencher_codigo_99(page, codigo):
        browser.close()
        return {"success": False, "reason": "localizador_invalido"}

    filled_code = preencher_codigo_99(page, codigo)
    if filled_code:
        for b in ["button[type='submit']", "button:has-text('Confirmar')", "button:has-text('Concluir a entrega')", "button:has-text('Continuar')"]:
            if try_click(page, b):
                break
        page.wait_for_timeout(1200)

    success = is_confirmation_page_99(page)
    browser.close()
    if success:
        return {"success": True, "message": "Entrega confirmada na 99Food!"}
    else:
        return {"success": False, "reason": "codigo_invalido" if filled_code else "erro_desconhecido"}

# ---------- Endpoints ----------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "online",
        "message": "ConfirmaTudo API está rodando!",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "confirmar": "POST /confirmar-entrega"
        }
    })

@app.route("/confirmar-entrega", methods=["POST"])
def confirmar_entrega():
    payload = request.get_json(force=True)
    localizador = (payload.get("localizador") or "").strip()
    codigo = (payload.get("codigo") or "").strip()

    if not localizador or not codigo:
        return jsonify({"error": "Localizador e código são obrigatórios"}), 400

    # normaliza para só dígitos
    localizador = "".join([c for c in localizador if c.isdigit()])
    codigo = "".join([c for c in codigo if c.isdigit()])

    try:
        with sync_playwright() as pw:
            # tenta iFood primeiro
            result_ifood = confirmar_ifood(pw, localizador, codigo)
            if result_ifood.get("success"):
                return jsonify({"plataforma": "iFood", **result_ifood}), 200

            # se não, tenta 99
            result_99 = confirmar_99(pw, localizador, codigo)
            if result_99.get("success"):
                return jsonify({"plataforma": "99Food", **result_99}), 200

            # se nenhum funcionou, devolve motivo mais provável
            reasons = {
                "localizador_invalido": "Localizador inválido (não avançou para tela de código).",
                "codigo_invalido": "Código inválido (não avançou para confirmação).",
                "erro_desconhecido": "Erro desconhecido durante o processo."
            }
            # escolhe principal razão se existir
            reason = result_ifood.get("reason") or result_99.get("reason") or "erro_desconhecido"
            return jsonify({"success": False, "reason": reason, "message": reasons.get(reason)}), 404
    except Exception as e:
        print("Erro geral:", e)
        return jsonify({"error": "Erro interno ao processar a solicitação."}), 500

if __name__ == "__main__":
    print(f"🚀 Servidor rodando em {BASE_URL} na porta {PORT}")
    app.run(host="0.0.0.0", port=PORT)
