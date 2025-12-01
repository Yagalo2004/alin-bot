import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import pandas as pd
import requests # <--- Nouvelle librairie pour parler à Telegram
import time

load_dotenv()
EMAIL = os.getenv("ALIN_EMAIL")
PASSWORD = os.getenv("ALIN_PASSWORD")
# On charge les clés Telegram
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FICHIER_HISTORIQUE = "historique.csv"

# --- FONCTION D'ENVOI TELEGRAM ---
def envoyer_notif(message):
    try:
        # L'URL magique de Telegram
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        # Les données à envoyer
        params = {
            "chat_id": TG_CHAT_ID,
            "text": message
        }
        # On envoie la requête
        requests.get(url, params=params)
    except Exception as e:
        print(f"Erreur envoi Telegram : {e}")

def run():
    print("🧠 Chargement de la mémoire...")
    deja_vus = []
    if os.path.exists(FICHIER_HISTORIQUE):
        try:
            df = pd.read_csv(FICHIER_HISTORIQUE)
            deja_vus = df["signature"].tolist()
        except:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        print("🌍 Connexion...")
        page.goto("https://al-in.fr/")
        
        try:
            page.get_by_role("button", name="Accepter tous les cookies").click(timeout=3000)
        except:
            pass
            
        page.get_by_role("link", name="Se connecter").click()
        page.wait_for_selector('[formcontrolname="mail"]', timeout=10000)
        page.fill('[formcontrolname="mail"]', EMAIL)
        page.fill('[formcontrolname="password"]', PASSWORD)
        page.get_by_role("button", name="JE ME CONNECTE").click()
        
        print("⏳ Analyse des offres...")
        try:
            page.wait_for_selector("text=Hors charge", timeout=15000)
        except:
            print("⚠️ Pas d'offres visibles.")

        elements_prix = page.locator("text=Hors charge").all()
        offres_du_jour = []
        nouvelles_offres_detectees = 0

        for element in elements_prix:
            try:
                carte_complete = element.locator("xpath=../../..")
                texte_brut = carte_complete.inner_text()
                signature = texte_brut.replace("\n", " | ").strip()
                offres_du_jour.append(signature)

                if signature in deja_vus:
                    print(".", end="", flush=True)
                else:
                    nouvelles_offres_detectees += 1
                    print(f"\n🚨 NOUVELLE OFFRE !")
                    
                    # --- ENVOI TELEGRAM ---
                    # On prépare un joli message
                    msg = f"🏠 NOUVELLE OFFRE AL-IN !\n\n{signature}\n\n👉 https://al-in.fr"
                    envoyer_notif(msg)
                    print("✅ Notification envoyée.")
                    # ----------------------
                    
            except Exception as e:
                pass

        print(f"\n📊 Fin. {nouvelles_offres_detectees} notifs envoyées.")
        browser.close()

    if len(offres_du_jour) > 0:
        df_save = pd.DataFrame(offres_du_jour, columns=["signature"])
        df_save.to_csv(FICHIER_HISTORIQUE, index=False)

if __name__ == "__main__":
    run()