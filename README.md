# SiNaPsE · TeslaMate Italiano + Custom Dashboards 🇮🇹

Distribuzione integrata di **TeslaMate**, dashboard Grafana ufficiali e **TeslaMate Custom Grafana Dashboards**, con le personalizzazioni italiane di SiNaPsEr0x.

**Un solo branch operativo e predefinito: `main`. Un solo workflow GitHub Actions. Un solo stack Docker Compose.**

## Componenti e provenienza

| Componente | Sorgente | Personalizzazioni di questa versione |
|---|---|---|
| Applicazione TeslaMate | [teslamate-org/teslamate](https://github.com/teslamate-org/teslamate) | Catalogo italiano completo per la release, verifica dei plurali `msgstr[0]` e `msgstr[1]`, navigazione Grafana in base alla lingua |
| Dashboard ufficiali | `grafana/dashboards/` | Copie italiane con UID `-it`, titoli e campi visualizzati tradotti, SQL e variabili tecniche conservati |
| Custom Dashboards | [jheredianet/Teslamate-CustomGrafanaDashboards](https://github.com/jheredianet/Teslamate-CustomGrafanaDashboards), importato in `custom/` | 15 dashboard italiane iniziali, dizionario e validatore dedicati, nessuna riscrittura degli alias SQL, collegamento di ritorno a TeslaMate garantito nelle copie generate |
| Grafana | Dockerfile della release TeslaMate con integrazioni locali | Dashboard ufficiali inglesi/italiane e cartella **Custom TeslaMate · Italiano**, datasource con UID esplicito `TeslaMate`, login obbligatorio, pubblicazione su `/grafana` |
| Traefik | `traefik:v3.6` nello stesso `compose.yml` | HTTPS su 443, redirect HTTP→HTTPS, HTTP/3, Let's Encrypt via HTTP challenge, routing TeslaMate/Grafana |
| Docker Compose | `compose.yml` nella radice | TeslaMate + Grafana + PostgreSQL 18 + Mosquitto + Traefik + generazione Basic Auth nello stesso stack |
| Aggiornamenti | Unico workflow `SiNaPsE · TeslaMate Italiano + Custom Dashboards` | Controllo di entrambi gli upstream, merge, validazione, test e pubblicazione transazionale su `main` |

La configurazione HTTPS segue l'architettura della guida ufficiale TeslaMate **Advanced installation with Traefik, Let's Encrypt & HTTP Basic Auth**: TeslaMate viene pubblicato su `https://FQDN/`, Grafana su `https://FQDN/grafana`, Traefik termina TLS e acquisisce automaticamente il certificato Let's Encrypt. In questa distribuzione anche la generazione del file Basic Auth e lo storage ACME sono integrati nello stack, quindi non servono un secondo compose, un file Traefik esterno o un `.htpasswd` creato a mano.

La migrazione iniziale applica le sole patch linguistiche del fork `SiNaPsEr0x/teslamate` alla release stabile **v4.3.0**, evitando di importare il codice `4.4.0-dev` presente nel vecchio branch. La base iniziale Customs è **v2026.10.15**. Le versioni, gli SHA immutabili e gli ID delle release effettivamente verificati sono registrati in [`.github/unified-state.json`](.github/unified-state.json): questo file è il riferimento aggiornato dopo ogni sincronizzazione.

La cronologia dei due progetti e delle personalizzazioni è conservata. I branch storici rimossi sono recuperabili attraverso i tag `archive/2026-10-18/…`. Il vecchio `patch-1` modificava soglie di una dashboard BatteryHealth ormai sostituita upstream: è conservato nel tag archivio, senza ripristinare una dashboard obsoleta. Il vecchio fork separato `SiNaPsEr0x/teslamate` resta disponibile come archivio di provenienza; l'installazione integrata è questa repository.

## Requisiti della configurazione Traefik

Prima di avviare lo stack servono:

- Docker Engine e Docker Compose v2, oppure Portainer su Docker Standalone;
- un **FQDN pubblico**, ad esempio `teslamate.example.com`;
- record DNS A/AAAA del FQDN verso il server;
- porte **80/TCP e 443/TCP** raggiungibili da Internet; **443/UDP** è usata da HTTP/3;
- un indirizzo email valido per Let's Encrypt;
- se il server è dietro un router/NAT, inoltro delle porte 80 e 443 verso l'host Docker.

Il certificato Let's Encrypt viene salvato nel volume Docker `traefik-acme`. TeslaMate e Grafana **non pubblicano più direttamente le porte 4000 e 3000 sull'host**: sono raggiungibili esclusivamente tramite Traefik. Mosquitto resta esposto solo su `127.0.0.1:1883` per eventuali integrazioni locali.

## Installazione con Portainer

Questa è la modalità consigliata se lo stack viene gestito da Portainer. Il `compose.yml` usa già le variabili `${...}` supportate da Portainer, quindi **non serve creare un file `.env` sul server**: i valori possono essere inseriti direttamente in **Stacks → Add stack → Environment variables** oppure caricati da un file `.env`.

Per uno stack collegato a Git usa:

```text
Repository:      https://github.com/SiNaPsEr0x/Teslamate-CustomGrafanaDashboards.git
Reference:       refs/heads/main
Compose path:    compose.yml
```

Il progetto usa **un solo FQDN**, impostato con `FQDN_TM`: TeslaMate risponde su `https://FQDN_TM/` e Grafana su `https://FQDN_TM/grafana`. Non serve un secondo FQDN per Grafana.

### Variabili da inserire nello stack Portainer

| Variabile | Esempio | Obbligatoria | Da conservare senza modificarla? | Uso |
|---|---|---:|---:|---|
| `ENCRYPTION_KEY` | valore casuale lungo | sì | **SÌ, critica** | cifra i dati sensibili TeslaMate; non rigenerarla su un database esistente |
| `DATABASE_USER` | `teslamate` | sì | sì | utente PostgreSQL |
| `DATABASE_PASS` | password casuale forte | sì | **sì** | password PostgreSQL usata da TeslaMate e Grafana |
| `DATABASE_NAME` | `teslamate` | sì | sì | database TeslaMate |
| `TM_TZ` | `Europe/Rome` | no | consigliato | timezone dello stack |
| `FQDN_TM` | `teslamate.example.com` | **sì** | sì | hostname pubblico usato da TeslaMate, Grafana e Traefik |
| `LETSENCRYPT_EMAIL` | `you@example.com` | **sì** | sì | account ACME/Let's Encrypt |
| `BASIC_AUTH_USER` | `teslamate` | no | sì | utente Basic Auth davanti a TeslaMate |
| `BASIC_AUTH_PASSWORD` | password casuale forte | **sì** | **sì** | password Basic Auth; genera automaticamente `.htpasswd` bcrypt |
| `GRAFANA_ADMIN_USER` | `admin` | no | sì | amministratore Grafana |
| `GRAFANA_ADMIN_PASSWORD` | password casuale forte | **sì** | **sì** | password iniziale/amministrativa Grafana |
| `MQTT_PORT` | `1883` | no | consigliato | porta MQTT pubblicata esclusivamente su localhost |

Per generare valori sicuri da un terminale Linux/macOS:

```bash
openssl rand -hex 32   # ENCRYPTION_KEY
openssl rand -hex 24   # DATABASE_PASS
openssl rand -hex 18   # BASIC_AUTH_PASSWORD
openssl rand -hex 24   # GRAFANA_ADMIN_PASSWORD
```

**Non usare la password dell'account Tesla come nessuna di queste variabili.**

### Cosa bisogna salvare prima di aggiornare, migrare o ricreare Portainer

Non considerare l'interfaccia di Portainer come unica copia delle credenziali. Conserva in un password manager o backup cifrato **l'intero set di variabili dello stack**, in particolare `ENCRYPTION_KEY`, `DATABASE_PASS`, `BASIC_AUTH_PASSWORD` e `GRAFANA_ADMIN_PASSWORD`.

Devi inoltre conservare:

1. **database TeslaMate**: backup del volume `teslamate-db` e, preferibilmente, anche un dump PostgreSQL consistente;
2. **dati Grafana**: volume `teslamate-grafana`;
3. **certificati Traefik**: volume `traefik-acme` — non è indispensabile per i dati TeslaMate, ma evita di richiedere di nuovo i certificati dopo un ripristino;
4. **MQTT**: `mosquitto-data` e `mosquitto-conf` se usi integrazioni che dipendono dallo stato/configurazione MQTT;
5. **Basic Auth**: `traefik-auth` può essere rigenerato automaticamente da `BASIC_AUTH_USER` e `BASIC_AUTH_PASSWORD`, quindi la cosa realmente importante è conservare quelle due variabili;
6. **commit installato**: annota lo SHA di `main` usato dall'installazione, utile per rollback e diagnosi.

Il dato più importante è `ENCRYPTION_KEY`: **se perdi o cambi quella chiave mantenendo il vecchio database, i dati sensibili cifrati da TeslaMate possono diventare inutilizzabili**. Non generare una nuova chiave durante un semplice redeploy, update dello stack o migrazione di Portainer.

### Aggiornare lo stack da Portainer

Quando aggiorni dal repository Git:

1. fai prima il backup di database, variabili Portainer e dati Grafana;
2. mantieni **identici** tutti i valori esistenti delle variabili, salvo modifiche intenzionali a FQDN/password;
3. aggiorna/redeploya lo stack dal branch `main`;
4. non eliminare i volumi persistenti durante il redeploy;
5. controlla i log di `proxy`, `teslamate`, `database` e `grafana` dopo l'avvio.

Portainer lascia i riferimenti `${FQDN_TM}`, `${DATABASE_PASS}`, ecc. nel Compose e applica i valori configurati nello stack al momento del deploy. Questo permette di aggiornare `compose.yml` dal repository senza hardcodare hostname o segreti nel Git.

## Installazione in un unico comando

Alternativa per chi non usa Portainer. Sostituisci soltanto `teslamate.example.com` e `you@example.com`, poi incolla l'intero comando:

```bash
FQDN_TM='teslamate.example.com' LETSENCRYPT_EMAIL='you@example.com' bash -c 'set -euo pipefail; git clone --depth 1 --branch main https://github.com/SiNaPsEr0x/Teslamate-CustomGrafanaDashboards.git; cd Teslamate-CustomGrafanaDashboards; ENCRYPTION_KEY="$(openssl rand -hex 32)"; DATABASE_PASS="$(openssl rand -hex 24)"; GRAFANA_ADMIN_PASSWORD="$(openssl rand -hex 24)"; BASIC_AUTH_PASSWORD="$(openssl rand -hex 18)"; printf "ENCRYPTION_KEY=%s\nDATABASE_USER=teslamate\nDATABASE_PASS=%s\nDATABASE_NAME=teslamate\nTM_TZ=Europe/Rome\nFQDN_TM=%s\nLETSENCRYPT_EMAIL=%s\nBASIC_AUTH_USER=teslamate\nBASIC_AUTH_PASSWORD=%s\nGRAFANA_ADMIN_USER=admin\nGRAFANA_ADMIN_PASSWORD=%s\nMQTT_PORT=1883\n" "$ENCRYPTION_KEY" "$DATABASE_PASS" "$FQDN_TM" "$LETSENCRYPT_EMAIL" "$BASIC_AUTH_PASSWORD" "$GRAFANA_ADMIN_PASSWORD" > .env; docker compose -f compose.yml config --quiet; docker compose -f compose.yml up -d --build --wait; docker compose -f compose.yml ps; printf "\nTeslaMate: https://%s/\nGrafana:   https://%s/grafana\nBasic Auth: teslamate / %s\nGrafana:    admin / %s\n" "$FQDN_TM" "$FQDN_TM" "$BASIC_AUTH_PASSWORD" "$GRAFANA_ADMIN_PASSWORD"'
```

Il comando:

1. clona `main`;
2. genera automaticamente chiave di cifratura e password casuali;
3. crea `.env`;
4. valida il modello Compose;
5. costruisce le immagini locali `sinapse/teslamate:local` e `sinapse/teslamate-grafana:local`;
6. genera automaticamente `/auth/.htpasswd` dentro un volume Docker usando bcrypt;
7. avvia PostgreSQL, Mosquitto, TeslaMate, Grafana e Traefik;
8. attende che le dipendenze richieste risultino pronte;
9. mostra URL e credenziali generate.

Le credenziali restano nel file locale `.env`, escluso da Git. **Non rigenerare `ENCRYPTION_KEY` su un'installazione esistente**, perché TeslaMate la usa per cifrare i dati sensibili.

## Come funziona lo stack all-in-one

### Traefik

Il servizio `proxy`:

- ascolta su 80 e 443;
- reindirizza HTTP verso HTTPS;
- usa il Docker provider con `exposedByDefault=false`;
- legge soltanto il socket Docker in modalità read-only;
- usa il resolver ACME `tmhttpchallenge`;
- salva i certificati nel volume `traefik-acme`;
- abilita HTTP/3 su 443/UDP.

### Basic Auth TeslaMate

Il servizio one-shot `basic-auth` usa l'immagine Apache `httpd:2.4-alpine` esclusivamente per eseguire `htpasswd -B`. Crea il file bcrypt nel volume `traefik-auth`; Traefik monta lo stesso volume in sola lettura. Il servizio `proxy` parte solo dopo che la generazione della password è terminata con successo.

La Basic Auth protegge TeslaMate su:

```text
https://FQDN/
```

Non utilizzare qui la password del proprio account Tesla.

### Grafana

Grafana è pubblicato sullo stesso dominio:

```text
https://FQDN/grafana
```

È configurato con:

- login Grafana obbligatorio;
- `GF_SERVER_ROOT_URL=https://%(domain)s/grafana`;
- `GF_SERVER_SERVE_FROM_SUB_PATH=true`;
- cookie secure;
- lingua predefinita italiana;
- datasource `TeslaMate` con UID stabile.

### TeslaMate

TeslaMate riceve `VIRTUAL_HOST=FQDN` e `CHECK_ORIGIN=true`, come previsto dalla configurazione reverse-proxy. Dopo il primo avvio entra in **Settings → URLs** e imposta:

```text
Web App:    https://FQDN
Dashboards: https://FQDN/grafana
```

Questo completa i collegamenti bidirezionali tra TeslaMate e Grafana.

## Volumi persistenti

Lo stack usa esclusivamente volumi Docker per i dati persistenti:

- `teslamate-db` → PostgreSQL 18;
- `teslamate-grafana` → dati Grafana;
- `mosquitto-conf` → configurazione MQTT;
- `mosquitto-data` → dati MQTT;
- `traefik-acme` → certificati Let's Encrypt;
- `traefik-auth` → file bcrypt generato per la Basic Auth.

Il database non espone PostgreSQL sulla rete host.

## Aggiornare una propria installazione

Il workflow aggiorna e verifica il repository. **Non si collega al server dell'utente e non aggiorna automaticamente i container già installati.**

Prima di aggiornare conserva backup del database, `.env` oppure delle variabili Portainer, versione/commit installato e dati Grafana. Un downgrade dei container non annulla eventuali migrazioni PostgreSQL: per un rollback con schema incompatibile serve il backup precedente.

```bash
cd Teslamate-CustomGrafanaDashboards
git pull --ff-only origin main
docker compose -f compose.yml config --quiet
docker compose -f compose.yml pull proxy basic-auth database mosquitto
docker compose -f compose.yml up -d --build --wait
docker compose -f compose.yml ps
docker compose -f compose.yml logs --tail=100 proxy teslamate grafana
```

**Migrazione dalla precedente configurazione senza Traefik:** conserva esattamente `ENCRYPTION_KEY`, `DATABASE_PASS`, `DATABASE_USER`, `DATABASE_NAME` e la password Grafana già usati. Aggiungi al `.env` oppure alle variabili Portainer `FQDN_TM`, `LETSENCRYPT_EMAIL`, `BASIC_AUTH_USER`, `BASIC_AUTH_PASSWORD` e `TM_TZ`. Dopo il passaggio, 4000/3000 non sono più pubblicate direttamente: usa gli URL HTTPS Traefik.

**Migrazione da un Compose/PostgreSQL precedente:** non collegare alla cieca vecchi volumi. PostgreSQL 18 usa il volume montato su `/var/lib/postgresql`, con sottocartella della versione; un volume PostgreSQL precedente montato su `/var/lib/postgresql/data` richiede una migrazione esplicita. Cambiare soltanto il percorso può far apparire un database vuoto.

## Unica automazione

Il workflow parte su push a `main`, manualmente e ogni giorno alle **06:23 UTC**; GitHub può ritardare le esecuzioni pianificate e può disabilitarle dopo 60 giorni di inattività del repository.

1. Risolve l'ultima release stabile pubblicata di entrambi gli upstream e verifica SHA e tag precedenti.
2. Prepara un candidato in un worktree temporaneo: merge normale per TeslaMate, merge con prefisso `custom/` per Customs. Le patch italiane restano nella cronologia locale.
3. Conserva traduzioni e infrastruttura della distribuzione; rigenera dashboard ufficiali e custom italiane. I workflow upstream importati non sono attivi: rimane un solo YAML in `.github/workflows/`.
4. Esegue controlli dei cataloghi, test Python, build dei due Dockerfile, suite Elixir inclusi test linguistici/plurali, validazione del Compose all-in-one con Traefik, migrazioni su database temporaneo, pianificazione SQL delle dashboard custom, avvio HTTP dell'applicazione e provisioning/API/healthcheck Grafana.
5. Pubblica su `main` soltanto dopo i controlli, con push ordinario. Non esegue rebase né force-push; un aggiornamento concorrente blocca la pubblicazione. I push di stato creati dal bot usano un gruppo di concorrenza separato e non possono più cancellare il run padre durante l'upload degli artefatti.

Errori, conflitti, tag spostati, traduzioni mancanti e incompatibilità generano una Issue dettagliata e lasciano il candidato non pubblicato. Nuove frasi non sono tradotte automaticamente per supposizione: la Issue elenca le voci da aggiungere ai dizionari. Una nuova release TeslaMate produce anche una Issue di revisione con il diff.

Gli artefatti `sinapse-teslamate-RUN_ID` contengono dashboard generate, report, log di build/test/migrazioni/SQL/Grafana e diff degli upstream. Durata: 30 giorni. L'upload degli artefatti usa l'azione corrente basata sul runtime Node 24.

## Struttura e licenze

- Radice, `elixir/`, `grafana/`, `rust/`: sorgenti TeslaMate e patch locali.
- `custom/`: progetto Customs completo, incluse traduzioni e documentazione originale.
- `config/grafana/`: provisioning integrato.
- `tools/`: importazione, sincronizzazione, validazione e test della distribuzione.
- `compose.yml`: stack all-in-one HTTPS.
- `.env.example`: elenco canonico delle variabili, utilizzabile anche come riferimento per Portainer.
- `docs/TESLAMATE-UPSTREAM.md`: README TeslaMate originale al momento dell'importazione.

TeslaMate mantiene la sua licenza **AGPL-3.0-or-later**, con `LICENSE` e `NOTICE` nella radice. Customs mantiene la propria licenza in `custom/LICENSE`. Questa distribuzione conserva i sorgenti e le attribuzioni dei rispettivi autori; non è una release ufficiale dei due progetti.

## Protezione del branch e autenticazione dell'automazione

L'aggiornamento usa la chiave deploy dedicata **SiNaPsE unified automatic updates**, limitata a questa repository. La parte privata è custodita nel Secret Actions `SINAPSE_UNIFIED_SYNC_SSH_KEY`; non è contenuta nei sorgenti o negli artefatti. Il token temporaneo `GITHUB_TOKEN` serve per interrogare le release e gestire le Issue.

Due ruleset proteggono `main`: uno vieta force-push e cancellazione senza eccezioni; l'altro mantiene revisione, approvazione dell'ultimo push e firme per i contributi ordinari, con bypass per amministratori e chiavi deploy. La chiave dedicata consente al workflow di pubblicare dopo le proprie verifiche senza richiedere ogni volta una PR. I push dell'automazione non avviano nuovamente il workflow operativo.

La precedente sincronizzazione generica del bot Pull è disabilitata con `.github/pull.yml`: il controllo dei due upstream è gestito dall'unico workflow della distribuzione.
