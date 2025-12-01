import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import pandas as pd
import requests
import time
from datetime import datetime # <--- Nouvel import pour gérer l'heure

load_dotenv()
EMAIL = os.getenv("ALIN_EMAIL")
PASSWORD = os.getenv("ALIN_PASSWORD")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FICHIER_HISTORIQUE = "historique.csv"

# --- FONCTIONS UTILES ---

def envoyer_notif(message):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        params = {"chat_id": TG_CHAT_ID, "text": message}
        requests.get(url, params=params)
    except Exception as e:
        print(f"Erreur Telegram : {e}")

# Modifié : on ajoute l'argument 'nom_onglet' pour savoir d'où vient l'offre
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
            
            # Si c'est nouveau, on crée un "pack" complet d'infos
            if signature not in deja_vus_signatures:
                # On capture la date et l'heure actuelles
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

# --- PROGRAMME PRINCIPAL ---

def run():
    print("🧠 Chargement de la mémoire...")
    
    # On prépare deux variables : 
    # 1. Le DataFrame complet (pour tout sauvegarder à la fin)
    # 2. La liste simple des signatures (pour vérifier rapidement si on connait déjà)
    
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
        # Pense à mettre headless=True pour GitHub Actions
        browser = p.chromium.launch(headless=True)
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
        
        print("⏳ Attente du tableau de bord...")
        page.wait_for_timeout(5000)

        # --- ANALYSE DES ONGLETS ---
        
        mots_cles_onglets = [
            "limitrophes", 
            "Autres communes"
        ]
        
        # Liste pour stocker les dictionnaires des nouvelles offres
        toutes_les_nouvelles_offres = [] 

        # 1. Onglet par défaut
        print("\n👉 Onglet par défaut...")
        nouveautes = analyser_la_page(page, deja_vus_signatures, "Communes demandées (Défaut)")
        toutes_les_nouvelles_offres.extend(nouveautes)

        # 2. Autres onglets
        for mot_cle in mots_cles_onglets:
            print(f"\n👉 Recherche onglet : '{mot_cle}'")
            try:
                onglet = page.locator("div").filter(has_text=mot_cle).last
                onglet.highlight()
                onglet.click()
                print("   ✅ Clic effectué.")
                
                print("   ⏳ Chargement (5s)...")
                time.sleep(5)
                
                # On passe le nom du mot clé comme "Source"
                nouveautes = analyser_la_page(page, deja_vus_signatures, mot_cle)
                print(f"   -> {len(nouveautes)} nouvelles offres ici.")
                
                toutes_les_nouvelles_offres.extend(nouveautes)
                
            except Exception as e:
                print(f"   ⚠️ Onglet '{mot_cle}' non trouvé ou vide.")

        # --- FIN ET SAUVEGARDE ---

        if len(toutes_les_nouvelles_offres) > 0:
            print(f"\n🚨 {len(toutes_les_nouvelles_offres)} NOUVEAUTÉS AU TOTAL !")
            
            # Envoi des notifs Telegram
            for offre in toutes_les_nouvelles_offres:
                # Attention : offre est maintenant un dictionnaire, il faut accéder au champ 'signature'
                signature_txt = offre['signature']
                onglet_txt = offre['onglet_source']
                
                message = f"🏠 ALERTE AL-IN ({onglet_txt}) !\n\n{signature_txt}\n\n👉 https://al-in.fr"
                envoyer_notif(message)
            
            # --- SAUVEGARDE INTELLIGENTE ---
            # 1. On transforme les nouvelles offres en DataFrame
            df_nouveautes = pd.DataFrame(toutes_les_nouvelles_offres)
            
            # 2. On colle les nouveautés à la suite de l'historique existant
            df_final = pd.concat([df_historique, df_nouveautes], ignore_index=True)
            
            # 3. On sauvegarde le tout
            df_final.to_csv(FICHIER_HISTORIQUE, index=False)
            print("💾 Historique étendu mis à jour (avec dates et onglets).")
            
        else:
            print("\n✅ Rien de nouveau.")

        browser.close()

if __name__ == "__main__":
    run()
