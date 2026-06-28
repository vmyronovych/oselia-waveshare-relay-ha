<!--
Canonical user-facing rollout text for blueprint changes.
Fill the placeholders before pasting into a PR body or release notes:
  <NEW_TAG>      e.g. v0.2.0  (used only in the legacy manual-import fallback)
  <BP_SUBPATH>   e.g. blueprints/automation/waveshare_relay/oselia_button_to_relay.yaml
  <SUMMARY_UA>   the release's issue/fix summary, written in Ukrainian
  <SUMMARY_EN>   the same issue/fix summary, written in English
Keep this file the single source of wording (see SKILL.md).

Layout: TWO root-level collapsible language blocks, each FULLY SELF-CONTAINED —
Ukrainian first (`<details open>`), English second (`<details>`). Inside each block:
(a) the issue summary, (b) the auto-delivery apply steps (update integration in HACS +
restart — the blueprint installs itself), (c) a nested collapsed legacy manual-import
fallback for users still on <= v0.1.x. GFM has no tabs; `<details>` is the equivalent.
Keep the <NEW_TAG>/<BP_SUBPATH> placeholders identical between the two languages.
-->

<details open>
<summary><b>🇺🇦 Українською — що змінилось і як оновитися</b></summary>

<br>

### Що виправляє цей реліз

<SUMMARY_UA>

### Як застосувати це оновлення

Блупринт **вбудовано в інтеграцію** і він встановлюється сам — імпортувати нічого не треба:

1. Оновіть **Waveshare Relay** у HACS (HACS → відкрийте інтеграцію → **Update** / **Redownload**)
   і **перезапустіть Home Assistant**.
2. Готово — під час перезапуску інтеграція записує новий блупринт у
   `/config/blueprints/automation/waveshare_relay/`. Ваші автоматизації зберігають свої
   параметри, змінювати нічого не потрібно.

> **Редагували блупринт самі?** Ваші зміни **не** перезаписуються — інтеграція їх зберігає і
> створює сповіщення в **Repairs** (Налаштування → Система → Виправлення), що є новіша версія.
> Щоб узяти нову версію — видаліть свою копію і перезапустіть HA (вона створиться заново); щоб
> і далі редагувати й отримувати оновлення — скопіюйте блупринт під власною назвою/шляхом і
> будуйте автоматизації з тієї копії (приватний шлях ніколи не перезаписується).

<details>
<summary>На старій версії (≤ v0.1.x, без авто-встановлення)?</summary>

<br>

Там блупринт треба імпортувати вручну. **Не** користуйтеся кнопкою ⋮ → «Re-import» (вона тягне
стару закріплену URL-адресу). Натомість: **Settings → Automations & Scenes → Blueprints →
Import Blueprint**, вставте URL версії **`<NEW_TAG>`** і **підтвердьте Overwrite**:
```
https://github.com/vmyronovych/oselia-waveshare-relay-ha/blob/<NEW_TAG>/<BP_SUBPATH>
```

</details>

</details>

<details>
<summary><b>🇬🇧 English — what changed and how to update</b></summary>

<br>

### What this release fixes

<SUMMARY_EN>

### How to apply this update

The blueprint is **bundled in the integration** and installs itself — there's nothing to import:

1. Update **Waveshare Relay** in HACS (HACS → open the integration → **Update** / **Redownload**)
   and **restart Home Assistant**.
2. That's it — on restart the integration writes the new blueprint to
   `/config/blueprints/automation/waveshare_relay/`. Your automations keep their inputs and
   need no changes.

> **Customized the blueprint yourself?** Your edits are **not** overwritten — the integration
> keeps them and raises a **Repairs** notice (Settings → System → Repairs) that a newer version
> exists. To take the new version, delete your copy and restart HA (it's re-created); to keep
> editing *and* get updates, copy the blueprint to your own name/path and build automations from
> that copy (a private path is never overwritten).

<details>
<summary>On an older build (≤ v0.1.x, before auto-install)?</summary>

<br>

There the blueprint must be imported by hand. **Don't** use ⋮ → "Re-import" (it re-fetches the
old pinned URL). Instead: **Settings → Automations & Scenes → Blueprints → Import Blueprint**,
paste the **`<NEW_TAG>`** URL and **confirm Overwrite**:
```
https://github.com/vmyronovych/oselia-waveshare-relay-ha/blob/<NEW_TAG>/<BP_SUBPATH>
```

</details>

</details>
