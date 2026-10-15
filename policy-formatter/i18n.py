"""
Fixed strings the PDF/Word templates draw themselves (contents heading, the
back-cover version card, month names) for each language a policy can be
translated into. Anything not listed falls back to English, so an unsupported
language still renders — it just keeps English card labels.

Only languages written in the Latin script are listed: the bundled Avenir /
Outfit fonts have no Greek, Cyrillic, Vietnamese or CJK glyphs, so a policy in
one of those would need a font added in brand.py first.
"""

_EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]

_BASE = {
    "contents": "Contents",
    "version_history": "Version history",
    "owner_approver": "Owner and approver",
    "version": "Version",
    "approval_date": "Approval date:",
    "owner": "Owner:",
    "approver": "Approver:",
    "update_field": "Right-click and choose “Update Field” to generate the table of contents.",
    "months": _EN_MONTHS,
    "month_fmt": "{month} {year}",
}

LANGUAGES = {
    "English": {},
    "Spanish": {
        "contents": "Contenido", "version_history": "Historial de versiones",
        "owner_approver": "Propietario y aprobador", "version": "Versión",
        "approval_date": "Fecha de aprobación:", "owner": "Propietario:", "approver": "Aprobador:",
        "update_field": "Haga clic con el botón derecho y elija “Actualizar campo” para generar el índice.",
        "months": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                   "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
        "month_fmt": "{month} de {year}",
    },
    "Danish": {
        "contents": "Indhold", "version_history": "Versionshistorik",
        "owner_approver": "Ejer og godkender", "version": "Version",
        "approval_date": "Godkendelsesdato:", "owner": "Ejer:", "approver": "Godkender:",
        "update_field": "Højreklik og vælg “Opdater felt” for at generere indholdsfortegnelsen.",
        "months": ["januar", "februar", "marts", "april", "maj", "juni", "juli",
                   "august", "september", "oktober", "november", "december"],
    },
    "Norwegian": {
        "contents": "Innhold", "version_history": "Versjonshistorikk",
        "owner_approver": "Eier og godkjenner", "version": "Versjon",
        "approval_date": "Godkjenningsdato:", "owner": "Eier:", "approver": "Godkjenner:",
        "update_field": "Høyreklikk og velg “Oppdater felt” for å lage innholdsfortegnelsen.",
        "months": ["januar", "februar", "mars", "april", "mai", "juni", "juli",
                   "august", "september", "oktober", "november", "desember"],
    },
    "Swedish": {
        "contents": "Innehåll", "version_history": "Versionshistorik",
        "owner_approver": "Ägare och godkännare", "version": "Version",
        "approval_date": "Godkännandedatum:", "owner": "Ägare:", "approver": "Godkännare:",
        "update_field": "Högerklicka och välj “Uppdatera fält” för att skapa innehållsförteckningen.",
        "months": ["januari", "februari", "mars", "april", "maj", "juni", "juli",
                   "augusti", "september", "oktober", "november", "december"],
    },
    "French": {
        "contents": "Sommaire", "version_history": "Historique des versions",
        "owner_approver": "Propriétaire et approbateur", "version": "Version",
        "approval_date": "Date d’approbation :", "owner": "Propriétaire :", "approver": "Approbateur :",
        "update_field": "Faites un clic droit et choisissez « Mettre à jour les champs » pour générer le sommaire.",
        "months": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
                   "août", "septembre", "octobre", "novembre", "décembre"],
    },
    "German": {
        "contents": "Inhalt", "version_history": "Versionsverlauf",
        "owner_approver": "Eigentümer und Genehmiger", "version": "Version",
        "approval_date": "Genehmigungsdatum:", "owner": "Eigentümer:", "approver": "Genehmiger:",
        "update_field": "Rechtsklick und „Feld aktualisieren“ wählen, um das Inhaltsverzeichnis zu erstellen.",
        "months": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                   "August", "September", "Oktober", "November", "Dezember"],
    },
    "Portuguese": {
        "contents": "Índice", "version_history": "Histórico de versões",
        "owner_approver": "Proprietário e aprovador", "version": "Versão",
        "approval_date": "Data de aprovação:", "owner": "Proprietário:", "approver": "Aprovador:",
        "update_field": "Clique com o botão direito e escolha “Atualizar campo” para gerar o índice.",
        "months": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
                   "agosto", "setembro", "outubro", "novembro", "dezembro"],
        "month_fmt": "{month} de {year}",
    },
    "Italian": {
        "contents": "Indice", "version_history": "Cronologia delle versioni",
        "owner_approver": "Proprietario e approvatore", "version": "Versione",
        "approval_date": "Data di approvazione:", "owner": "Proprietario:", "approver": "Approvatore:",
        "update_field": "Fare clic con il pulsante destro e scegliere “Aggiorna campo” per generare l’indice.",
        "months": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
                   "agosto", "settembre", "ottobre", "novembre", "dicembre"],
    },
    "Dutch": {
        "contents": "Inhoud", "version_history": "Versiegeschiedenis",
        "owner_approver": "Eigenaar en goedkeurder", "version": "Versie",
        "approval_date": "Goedkeuringsdatum:", "owner": "Eigenaar:", "approver": "Goedkeurder:",
        "update_field": "Klik met de rechtermuisknop en kies “Veld bijwerken” om de inhoudsopgave te maken.",
        "months": ["januari", "februari", "maart", "april", "mei", "juni", "juli",
                   "augustus", "september", "oktober", "november", "december"],
    },
    "Polish": {
        "contents": "Spis treści", "version_history": "Historia wersji",
        "owner_approver": "Właściciel i zatwierdzający", "version": "Wersja",
        "approval_date": "Data zatwierdzenia:", "owner": "Właściciel:", "approver": "Zatwierdzający:",
        "update_field": "Kliknij prawym przyciskiem myszy i wybierz „Aktualizuj pole”, aby wygenerować spis treści.",
        "months": ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca",
                   "sierpnia", "września", "października", "listopada", "grudnia"],
    },
    "Turkish": {
        "contents": "İçindekiler", "version_history": "Sürüm geçmişi",
        "owner_approver": "Sahip ve onaylayan", "version": "Sürüm",
        "approval_date": "Onay tarihi:", "owner": "Sahip:", "approver": "Onaylayan:",
        "update_field": "Sağ tıklayın ve içindekiler tablosunu oluşturmak için “Alanı Güncelle” seçin.",
        "months": ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
                   "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"],
    },
}

# Language -> short code, used for translation policy ids ("<root>--es").
CODES = {
    "English": "en", "Spanish": "es", "Danish": "da", "Norwegian": "no", "Swedish": "sv",
    "French": "fr", "German": "de", "Portuguese": "pt", "Italian": "it", "Dutch": "nl",
    "Polish": "pl", "Turkish": "tr",
}


def strings(language):
    """Full string table for a language (missing keys fall back to English)."""
    out = dict(_BASE)
    out.update(LANGUAGES.get(language or "English", {}))
    return out


def t(policy_or_language, key):
    lang = policy_or_language if isinstance(policy_or_language, str) else getattr(policy_or_language, "language", "English")
    return strings(lang)[key]


def month_year(language, ym):
    """'2026-10' -> 'October 2026' / 'octubre de 2026' ... (ym = YYYY-MM)."""
    s = strings(language)
    year, _, month = ym.partition("-")
    try:
        name = s["months"][int(month) - 1]
    except (ValueError, IndexError):
        return ym
    return s["month_fmt"].format(month=name, year=year)


def localise_version(language, version):
    """'Version 1:' -> 'Versión 1:' (only the leading word changes)."""
    word = t(language, "version")
    return word + version[len("Version"):] if version.startswith("Version") else version
