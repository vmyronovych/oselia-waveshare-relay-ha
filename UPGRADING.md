# Applying an update · Як застосувати оновлення

The canonical guide for updating the **Waveshare Modbus RTU Relay** integration. Every
release links here. For most people an update is two clicks; the steps below also cover the
blueprint and the rare "I customized it" case.

<details open>
<summary><b>🇺🇦 Українською</b></summary>

<br>

### 1. Оновіть інтеграцію
HACS → відкрийте **Waveshare Relay** → **Update** (або ⋮ → **Redownload**) →
**перезапустіть Home Assistant**.

### 2. Блупринт — робити нічого не треба
Блупринт вбудований в інтеграцію і під час перезапуску записується у
`/config/blueprints/automation/vmyronovych/`. Оновлення приходить разом з інтеграцією —
**імпортувати вручну не потрібно**. Ваші автоматизації зберігають свої параметри.

### 3. Якщо ви редагували блупринт під себе
Ваш файл **ніколи не перезаписується**. Коли виходить новіша версія, з'являється сповіщення
в **Settings → System → Repairs** (Виправлення) з вибором:
- **Взяти нову версію** — ваш файл зберігається у `*.bak`, потім замінюється новим.
- **Залишити мою версію** — ваші зміни лишаються; нагадаємо лише коли вийде ще новіша версія.

Щоб налаштовувати блупринт **і** завжди отримувати оновлення без конфліктів — скопіюйте його
під власною назвою/шляхом і будуйте автоматизації з тієї копії (приватну копію ми не чіпаємо).

### 4. На старих збірках (≤ v0.1.x)
Ті версії не мають авто-встановлення — імпортуйте блупринт **один раз**:
**Settings → Automations & Scenes → Blueprints → Import Blueprint**, вставте URL і
підтвердьте **Overwrite**:
```
https://github.com/vmyronovych/oselia-waveshare-relay-ha/blob/main/blueprints/automation/vmyronovych/oselia_button_to_relay.yaml
```
Після оновлення до v0.2.1+ далі все автоматично.

### Перевірка
Блупринт видно у **Settings → Automations → Blueprints**; ваші автоматизації працюють.

</details>

<details>
<summary><b>🇬🇧 English</b></summary>

<br>

### 1. Update the integration
HACS → open **Waveshare Relay** → **Update** (or ⋮ → **Redownload**) → **restart Home
Assistant**.

### 2. The blueprint — nothing to do
The blueprint is bundled in the integration and written to
`/config/blueprints/automation/vmyronovych/` on restart. Updates ride along with the
integration — **no manual import**. Your automations keep their inputs.

### 3. If you customized the blueprint
Your file is **never overwritten**. When a newer version ships you get a notice in
**Settings → System → Repairs** with a choice:
- **Take the new version** — your file is backed up to `*.bak`, then replaced.
- **Keep my version** — your edits stay; you're reminded again only when a newer version ships.

To customize **and** always get updates conflict-free, copy the blueprint to your own
name/path and build automations from that copy (a private copy is never touched).

### 4. On older builds (≤ v0.1.x)
Those predate auto-install — import the blueprint **once**:
**Settings → Automations & Scenes → Blueprints → Import Blueprint**, paste the URL and
confirm **Overwrite**:
```
https://github.com/vmyronovych/oselia-waveshare-relay-ha/blob/main/blueprints/automation/vmyronovych/oselia_button_to_relay.yaml
```
After updating to v0.2.1+ it's automatic from then on.

### Verify
The blueprint shows under **Settings → Automations → Blueprints**; your automations work.

</details>
