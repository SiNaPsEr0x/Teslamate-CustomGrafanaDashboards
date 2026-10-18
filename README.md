# TeslaMate Italiano + Custom Dashboards 🇮🇹

**TeslaMate e Grafana in italiano, pronti per Docker o Portainer.** Questa distribuzione unisce [TeslaMate ufficiale](https://github.com/teslamate-org/teslamate) e [Custom Grafana Dashboards](https://github.com/jheredianet/Teslamate-CustomGrafanaDashboards), con dashboard italiane, Traefik e HTTPS.

**In breve:** un solo repository, branch `main`, un solo `compose.yml`. Gli aggiornamenti dei sorgenti e le patch italiane sono gestiti automaticamente su GitHub. **Il tuo server non si aggiorna da solo:** per installare una nuova versione devi aggiornare lo stack.

## Prima di iniziare

Ti servono:
- Docker con Compose oppure **Portainer** su Docker Standalone.
- Un dominio, ad esempio `teslamate.example.com`, che punti al tuo server.
- Porte Internet **80/TCP e 443/TCP** inoltrate al server (443/UDP facoltativa per HTTP/3). Servono per HTTPS e Let's Encrypt.
- Un'email valida e **quattro valori segreti**: chiave di cifratura, password database, password di accesso TeslaMate e password amministratore Grafana.

> **Attenzione:** se stai aggiornando un'installazione esistente, **riutilizza la stessa `ENCRYPTION_KEY` e le stesse credenziali del database**. Non eliminare i volumi Docker: contengono i tuoi dati.

## Installazione consigliata: Portainer

1. Apri **Stacks → Add stack → Repository**.
2. Inserisci questi valori:

   | Campo Portainer | Valore |
   |---|---|
   | Repository URL | `https://github.com/SiNaPsEr0x/Teslamate-CustomGrafanaDashboards.git` |
   | Repository reference | `refs/heads/main` |
   | Compose path | `compose.yml` |

3. In **Environment variables**, inserisci le variabili qui sotto. Puoi copiare i nomi da [`.env.example`](.env.example).

   | Variabile | Cosa inserire |
   |---|---|
   | `FQDN_TM` | Il tuo dominio, **senza** `https://` |
   | `LETSENCRYPT_EMAIL` | La tua email |
   | `ENCRYPTION_KEY` | Chiave casuale lunga, da conservare |
   | `DATABASE_PASS` | Password forte per PostgreSQL |
   | `BASIC_AUTH_PASSWORD` | Password per aprire TeslaMate |
   | `GRAFANA_ADMIN_PASSWORD` | Password amministratore Grafana |

   Le altre variabili hanno già valori predefiniti: `DATABASE_USER=teslamate`, `DATABASE_NAME=teslamate`, `TM_TZ=Europe/Rome`, `BASIC_AUTH_USER=teslamate`, `GRAFANA_ADMIN_USER=admin`, `HTTP_PORT=80`, `HTTPS_PORT=443`, `MQTT_PORT=1883`.

   Per generare i quattro valori casuali su Linux/macOS, esegui `openssl rand -hex 32` quattro volte. **Non usare la password del tuo account Tesla.**

4. Premi **Deploy the stack**. La prima compilazione può richiedere alcuni minuti.

### Dopo l'avvio

- **TeslaMate:** `https://TUO-DOMINIO/` — utente Basic Auth `teslamate`, password `BASIC_AUTH_PASSWORD`.
- **Grafana:** `https://TUO-DOMINIO/grafana` — utente `admin`, password `GRAFANA_ADMIN_PASSWORD`.
- In TeslaMate, apri **Settings → URLs** e imposta:
  - Web App: `https://TUO-DOMINIO`
  - Dashboards: `https://TUO-DOMINIO/grafana`

`TUO-DOMINIO` significa il valore che hai inserito in `FQDN_TM`.

### Se le porte 80 e 443 sono già occupate sul NAS

Imposta per esempio `HTTP_PORT=8080` e `HTTPS_PORT=8443` nelle variabili Portainer. **Sul router** inoltra comunque la porta Internet **80 → NAS:8080** e **443 → NAS:8443**. Gli indirizzi da aprire rimangono `https://TUO-DOMINIO/` e `https://TUO-DOMINIO/grafana`.

## Installazione senza Portainer

```bash
git clone https://github.com/SiNaPsEr0x/Teslamate-CustomGrafanaDashboards.git
cd Teslamate-CustomGrafanaDashboards
cp .env.example .env
```

Apri `.env`, sostituisci i valori `replace-with-...`, il dominio e l'email; conserva il file in un luogo sicuro. Poi avvia:

```bash
docker compose -f compose.yml up -d --build --wait
```

## Aggiornamenti e backup

**Il repository si aggiorna automaticamente:** GitHub Actions controlla ogni giorno le release stabili dei due progetti, applica le patch italiane, esegue i test e pubblica su `main` soltanto se i controlli passano.

**Per aggiornare il tuo server:**
- **Portainer:** fai un backup, poi aggiorna/redeploya lo stack dal repository Git, **senza cancellare i volumi** e senza cambiare le variabili esistenti.
- **Docker Compose:** fai un backup, poi esegui:

```bash
git pull --ff-only origin main
docker compose -f compose.yml up -d --build --wait
```

**Prima di aggiornare o migrare**, salva il database PostgreSQL (preferibilmente con un dump), i dati Grafana e tutte le variabili/credenziali dello stack. In particolare, **non perdere mai `ENCRYPTION_KEY`**: serve a leggere i dati sensibili già cifrati.

> **Installazioni precedenti:** se arrivi da un altro Compose o da una versione precedente di PostgreSQL, verifica la migrazione del database prima di collegare i vecchi volumi. Non basta cambiare il percorso del volume.

## Problemi più comuni

| Problema | Cosa controllare |
|---|---|
| HTTPS non funziona | DNS del dominio e inoltro della porta Internet 80/TCP e 443/TCP |
| TeslaMate chiede una password | È la Basic Auth: utente `teslamate`, password `BASIC_AUTH_PASSWORD` |
| Grafana chiede un login | Utente `admin`, password `GRAFANA_ADMIN_PASSWORD` |
| Dopo l'aggiornamento mancano i dati | Controlla i volumi e le credenziali **prima** di inizializzare un nuovo database |
| Lo stack non parte | Controlla i log dei container in Portainer o con `docker compose logs --tail=100` |

## Crediti e dettagli tecnici

Questo progetto **non è una release ufficiale** di TeslaMate o Custom Dashboards. Mantiene le licenze originali: [TeslaMate](LICENSE) (AGPL-3.0-or-later) e [Custom Dashboards](custom/LICENSE).

Per le impostazioni disponibili consulta [`.env.example`](.env.example); per il codice originale di TeslaMate consulta [la documentazione upstream](docs/TESLAMATE-UPSTREAM.md). I dettagli delle versioni sincronizzate sono in [`.github/unified-state.json`](.github/unified-state.json), mentre i test automatici sono visibili in [GitHub Actions](https://github.com/SiNaPsEr0x/Teslamate-CustomGrafanaDashboards/actions).
