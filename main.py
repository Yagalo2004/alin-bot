import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import pandas as pd
import requests
import time
from datetime import datetime

# --- CONFIGURATION ---
load_dotenv()
EMAIL = os.getenv("ALIN_EMAIL")
PASSWORD = os.getenv("ALIN_PASSWORD")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FICHIER_HISTORIQUE = "historique.csv"

URL_INLI = "https://www.inli.fr/locations/offres/ile-de-france-region_r:11?price_min=0&price_max=1000&area_min=0&area_max=250&room_min=0&room_max=5&bedroom_min=1&bedroom_max=5" 

# --- FONCTIONS UTILES ---

def envoyer_notif(message):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        params = {"chat_id": TG_CHAT_ID, "text": message}
        requests.get(url, params=params)
    except Exception as e:
        print(f"Erreur Telegram : {e}")

# Fonction pour scraper AL-IN
def analyser_la_page(page, deja_vus_signatures, nom_onglet):
    offres_structurees = []
    try:
        page.wait_for_timeout(3000) 
    except:
        pass

    elements_prix = page.locator("text=Hors charge").all()
    
    for element in elements_prix:
        try:
            carte_complete = element.locator("xpath=../../..")
            texte_brut = carte_complete.inner_text()
            signature = texte_brut.replace("\n", " | ").strip()
            
            if signature not in deja_vus_signatures:
                date_actuelle = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                info_offre = {
                    "signature": signature,
                    "date_detection": date_actuelle,
                    "onglet_source": nom_onglet
                }
                offres_structurees.append(info_offre)
        except:
            pass
            
    return offres_structurees

# Fonction pour scraper IN'LI (Je l'ai remontée ICI pour qu'elle soit connue avant le run)
def scraper_inli(page, deja_vus_signatures):
    offres = []
    print("\n🌍 Passage sur In'li...")
    try:
        page.goto(URL_INLI)
        try:
            page.get_by_role("button", name="Tout refuser").click(timeout=3000)
        except:
            pass
        
        print("⏳ Chargement In'li (5s)...")
        time.sleep(5)
        
        elements = page.locator("text=€").all()
        
        for element in elements:
            try:
                texte = element.inner_text()
                if "€" in texte and len(texte) < 20: 
                    carte = element.locator("xpath=../..") 
                    signature = carte.inner_text().replace("\n", " | ").strip()
                    
                    if len(signature) > 20 and signature not in deja_vus_signatures:
                        offres.append({
                            "signature": signature,
                            "date_detection": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "onglet_source": "IN'LI"
                        })
            except:
                pass
    except Exception as e:
        print(f"⚠️ Erreur sur In'li : {e}")
        
    print(f"   -> {len(offres)} nouveautés trouvées sur In'li.")
    return offres

# --- PROGRAMME PRINCIPAL ---

def run():
    print("🧠 Chargement de la mémoire...")
    
    df_historique = pd.DataFrame(columns=["signature", "date_detection", "onglet_source"])
    deja_vus_signatures = []

    if os.path.exists(FICHIER_HISTORIQUE):
        try:
            df_historique = pd.read_csv(FICHIER_HISTORIQUE)
            deja_vus_signatures = df_historique["signature"].tolist()
            print(f"   -> {len(deja_vus_signatures)} offres déjà en mémoire.")
        except:
            print("   -> Fichier historique illisible ou vide.")

    with sync_playwright() as p:
        # Pense à remettre headless=True pour GitHub Actions !
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # --- PARTIE 1 : AL-IN ---
        print("🚀 Démarrage mission AL-IN...")
        try:
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
            
            print("⏳ Attente du tableau de bord...")
            page.wait_for_timeout(5000)

            toutes_les_nouvelles_offres = [] 

            # Onglet par défaut
            print("\n👉 Onglet par défaut...")
            nouveautes = analyser_la_page(page, deja_vus_signatures, "Communes demandées (Défaut)")
            toutes_les_nouvelles_offres.extend(nouveautes)

            # Autres onglets
            mots_cles_onglets = ["limitrophes", "Autres communes"]
            for mot_cle in mots_cles_onglets:
                print(f"\n👉 Recherche onglet : '{mot_cle}'")
                try:
                    onglet = page.locator("div").filter(has_text=mot_cle).last
                    onglet.highlight()
                    onglet.click()
                    print("   ✅ Clic effectué.")
                    print("   ⏳ Chargement (5s)...")
                    time.sleep(5)
                    nouveautes = analyser_la_page(page, deja_vus_signatures, mot_cle)
                    print(f"   -> {len(nouveautes)} nouvelles offres ici.")
                    toutes_les_nouvelles_offres.extend(nouveautes)
                except Exception as e:
                    print(f"   ⚠️ Onglet '{mot_cle}' non trouvé ou vide.")
        except Exception as e:
            print(f"❌ Erreur générale sur Al-in : {e}")

        # --- PARTIE 2 : IN'LI ---
        
        # On met à jour la liste des signatures connues
        signatures_connues_a_jour = deja_vus_signatures + [o['signature'] for o in toutes_les_nouvelles_offres]
        
        # On lance le scraper In'li
        nouveautes_inli = scraper_inli(page, signatures_connues_a_jour)
        toutes_les_nouvelles_offres.extend(nouveautes_inli)

        # --- FIN ET SAUVEGARDE ---

        if len(toutes_les_nouvelles_offres) > 0:
            print(f"\n🚨 {len(toutes_les_nouvelles_offres)} NOUVEAUTÉS AU TOTAL (Al-in + In'li) !")
            
            for offre in toutes_les_nouvelles_offres:
                signature_txt = offre['signature']
                onglet_txt = offre['onglet_source']
                
                # Le titre change selon la source
                message = f"🏠 ALERTE {onglet_txt} !\n\n{signature_txt}\n\n👉 Al-in.fr ou Inli.fr"
                envoyer_notif(message)
            
            # Sauvegarde
            df_nouveautes = pd.DataFrame(toutes_les_nouvelles_offres)
            df_final = pd.concat([df_historique, df_nouveautes], ignore_index=True)
            df_final.to_csv(FICHIER_HISTORIQUE, index=False)
            print("💾 Historique étendu mis à jour.")
            
        else:
            print("\n✅ Rien de nouveau sur aucun site.")

        browser.close()

if __name__ == "__main__":
    run()
