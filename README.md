# TeslaMate Italiano + Custom Dashboards 🇮🇹

**TeslaMate e Grafana in italiano, pronti per Docker Compose o Portainer.** Questa distribuzione unisce [TeslaMate ufficiale](https://github.com/teslamate-org/teslamate) e [Custom Grafana Dashboards](https://github.com/jheredianet/Teslamate-CustomGrafanaDashboards), con dashboard italiane, Traefik e HTTPS.

## La versione SiNaPsE in breve

- **Un solo repository GitHub**: questo.
- **Una sola immagine Docker personalizzata**: `ghcr.io/sinapser0x/teslamate:latest`.
- La stessa immagine contiene **TeslaMate + Grafana + dashboard/localizzazioni italiane**.
- Docker Compose avvia TeslaMate e Grafana come servizi separati dalla stessa immagine, così restano isolati e riavviabili indipendentemente.
- PostgreSQL, MQTT e Traefik restano immagini ufficiali separate gestite automaticamente dal Compose.
- **Un solo comando** per scaricare/aggiornare e avviare tutto:

```bash
docker compose -f compose.yml up -d --pull always --wait
```

Gli aggiornamenti dei sorgenti e le patch italiane vengono verificati automaticamente da GitHub Actions; solo dopo il superamento dei test viene aggiornata l'immagine `ghcr.io/sinapser0x/teslamate:latest`.

## Prima di iniziare

Ti servono:
- Docker con Compose oppure **Portainer** su Docker Standalone.
- Un dominio, ad esempio `teslamate.example.com`, che punti al tuo server.
- Porte Internet **80/TCP e 443/TCP** inoltrate al server (443/UDP facoltativa per HTTP/3).
- Un'email valida e quattro valori segreti: chiave di cifratura, password database, password di accesso TeslaMate e password amministratore Grafana.

> **Attenzione:** se stai aggiornando un'installazione esistente, riutilizza la stessa `ENCRYPTION_KEY` e le stesse credenziali del database. Non eliminare i volumi Docker: contengono i tuoi dati.

## Installazione consigliata: Portainer

1. Apri **Stacks → Add stack → Repository**.
2. Inserisci:

   | Campo Portainer | Valore |
   |---|---|
   | Repository URL | `https://github.com/SiNaPsEr0x/Teslamate-CustomGrafanaDashboards.git` |
   | Repository reference | `refs/heads/main` |
   | Compose path | `compose.yml` |

3. In **Environment variables** inserisci almeno:

   | Variabile | Cosa inserire |
   |---|---|
   | `FQDN_TM` | Il tuo dominio, senza `https://` |
   | `LETSENCRYPT_EMAIL` | La tua email |
   | `ENCRYPTION_KEY` | Chiave casuale lunga, da conservare |
   | `DATABASE_PASS` | Password forte per PostgreSQL |
   | `BASIC_AUTH_PASSWORD` | Password per aprire TeslaMate |
   | `GRAFANA_ADMIN_PASSWORD` | Password amministratore Grafana |

   Le altre variabili hanno valori predefiniti: `DATABASE_USER=teslamate`, `DATABASE_NAME=teslamate`, `TM_TZ=Europe/Rome`, `BASIC_AUTH_USER=teslamate`, `GRAFANA_ADMIN_USER=admin`, `HTTP_PORT=80`, `HTTPS_PORT=443`, `MQTT_PORT=1883`.

4. Premi **Deploy the stack**. Portainer scaricherà la singola immagine SiNaPsE e le immagini ufficiali richieste dal Compose.

### Dopo l'avvio

- **TeslaMate:** `https://TUO-DOMINIO/` — utente Basic Auth `teslamate`, password `BASIC_AUTH_PASSWORD`.
- **Grafana:** `https://TUO-DOMINIO/grafana` — utente `admin`, password `GRAFANA_ADMIN_PASSWORD`.
- In TeslaMate, apri **Settings → URLs** e imposta:
  - Web App: `https://TUO-DOMINIO`
  - Dashboards: `https://TUO-DOMINIO/grafana`

`TUO-DOMINIO` è il valore inserito in `FQDN_TM`.

### Se le porte 80 e 443 sono già occupate sul NAS

Imposta per esempio `HTTP_PORT=8080` e `HTTPS_PORT=8443`. Sul router inoltra comunque la porta Internet **80 → NAS:8080** e **443 → NAS:8443**. Gli indirizzi restano `https://TUO-DOMINIO/` e `https://TUO-DOMINIO/grafana`.

## Installazione Docker Compose

La configurazione iniziale si fa una sola volta:

```bash
git clone https://github.com/SiNaPsEr0x/Teslamate-CustomGrafanaDashboards.git
cd Teslamate-CustomGrafanaDashboards
cp .env.example .env
```

Modifica `.env` con dominio, email e password. Da quel momento installazione/aggiornamento/avvio si fanno con **un solo comando**:

```bash
docker compose -f compose.yml up -d --pull always --wait
```

Lo stesso comando può essere riutilizzato in futuro: Docker Compose scarica l'immagine più recente, ricrea solo ciò che è cambiato e conserva i volumi.

## Architettura Docker

```text
SiNaPsEr0x/Teslamate-CustomGrafanaDashboards
        │
        └── ghcr.io/sinapser0x/teslamate:latest
                 ├── servizio Compose: teslamate
                 └── servizio Compose: grafana

compose.yml
  ├── teslamate  ─┐
  ├── grafana    ─┴─ stessa immagine SiNaPsE
  ├── database     → PostgreSQL ufficiale
  ├── mosquitto    → Eclipse Mosquitto ufficiale
  └── proxy        → Traefik ufficiale
```

Quindi **non servono due pacchetti Docker personalizzati**. Il vecchio pacchetto Grafana separato non è più necessario per questa distribuzione.

## Aggiornamenti e backup

GitHub Actions controlla ogni giorno i due progetti upstream, applica le patch italiane, esegue i test applicativi, le migrazioni, i controlli SQL e l'avvio reale di TeslaMate e Grafana. Se tutto passa, pubblica la nuova singola immagine su GHCR.

Prima di aggiornare o migrare, salva il database PostgreSQL, i dati Grafana e tutte le variabili/credenziali dello stack. In particolare, **non perdere mai `ENCRYPTION_KEY`**.

> Se arrivi da un altro Compose o da una versione precedente di PostgreSQL, verifica la migrazione del database prima di collegare i vecchi volumi.

## Problemi più comuni

| Problema | Cosa controllare |
|---|---|
| HTTPS non funziona | DNS del dominio e inoltro delle porte Internet 80/TCP e 443/TCP |
| TeslaMate chiede una password | Basic Auth: utente `teslamate`, password `BASIC_AUTH_PASSWORD` |
| Grafana chiede un login | Utente `admin`, password `GRAFANA_ADMIN_PASSWORD` |
| Dopo l'aggiornamento mancano i dati | Controlla volumi e credenziali prima di inizializzare un nuovo database |
| Lo stack non parte | `docker compose logs --tail=100` oppure i log dei container in Portainer |

## Crediti e dettagli tecnici

Questo progetto **non è una release ufficiale** di TeslaMate o Custom Dashboards. Mantiene le licenze originali: [TeslaMate](LICENSE) (AGPL-3.0-or-later) e [Custom Dashboards](custom/LICENSE).

Per le impostazioni consulta [`.env.example`](.env.example). I dettagli delle versioni sincronizzate sono in [`.github/unified-state.json`](.github/unified-state.json), mentre i test automatici sono visibili in [GitHub Actions](https://github.com/SiNaPsEr0x/Teslamate-CustomGrafanaDashboards/actions).
