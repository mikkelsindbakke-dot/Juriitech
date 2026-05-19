"""
Tests for processor.udpak_zip_til_filer.

Funktionen returnerer (filer, fejl)-tuple. fejl er en brugervenlig
streng der UI'et kan vise direkte til brugeren — fx for krypterede
zips ("Pak filen ud manuelt"). Vi tester at:
  - en valid zip → (filer, None)
  - en korrupt zip → ([], "kunne ikke åbne ...")
  - en zip kun med skjulte/__MACOSX-filer → ([], None) (bevidst — ingen
    fejl, bare ingen brugbare filer)

Krypterede zips kan ikke nemt konstrueres med stdlib zipfile (den
understøtter ikke at SKRIVE krypterede entries), så vi tester ikke det
specifikke flow her — DET SAMME kodesti rammes når BadZipFile/
RuntimeError fanges, og vi har dækket fejl-stien via corrupt-zip.
"""
import zipfile
from io import BytesIO

import pytest

from processor import udpak_zip_til_filer


pytestmark = pytest.mark.logic


def _byg_simpel_zip(filer: dict) -> bytes:
    """Lav en zip i memory med givne {filnavn: bytes}-mapping."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for navn, data in filer.items():
            z.writestr(navn, data)
    return buf.getvalue()


class TestValidZip:
    def test_returnerer_filer_og_None_fejl(self):
        zip_bytes = _byg_simpel_zip({
            "klage.pdf": b"%PDF-1.4 dummy",
            "bilag.docx": b"PK\x03\x04 dummy",
        })
        filer, fejl = udpak_zip_til_filer(zip_bytes)
        assert fejl is None
        assert len(filer) == 2
        navne = {n for n, _ in filer}
        assert "klage.pdf" in navne
        assert "bilag.docx" in navne

    def test_springer_macos_metadata_over(self):
        zip_bytes = _byg_simpel_zip({
            "__MACOSX/._klage.pdf": b"metadata-skrald",
            "klage.pdf": b"%PDF-1.4 dummy",
        })
        filer, fejl = udpak_zip_til_filer(zip_bytes)
        assert fejl is None
        assert len(filer) == 1
        assert filer[0][0] == "klage.pdf"

    def test_springer_skjulte_filer_over(self):
        zip_bytes = _byg_simpel_zip({
            ".DS_Store": b"junk",
            "klage.pdf": b"%PDF-1.4 dummy",
        })
        filer, fejl = udpak_zip_til_filer(zip_bytes)
        assert fejl is None
        assert len(filer) == 1


class TestUgyldigZip:
    def test_korrupt_zip_returnerer_brugbar_fejl(self):
        # Random bytes der ikke er en zip
        filer, fejl = udpak_zip_til_filer(b"jeg er ikke en zip-fil")
        assert filer == []
        assert fejl is not None
        # Fejlen skal indeholde aktiv handling brugeren kan udføre
        assert "pak filen ud" in fejl.lower() or "upload" in fejl.lower()

    def test_tom_input_returnerer_fejl(self):
        filer, fejl = udpak_zip_til_filer(b"")
        assert filer == []
        assert fejl is not None


class TestKrypteretDetektion:
    """
    Stdlib zipfile understøtter ikke at SKRIVE krypterede entries, så
    vi kan ikke nemt konstruere en ægte krypteret zip i en unit-test.
    Vi mocker i stedet ZipInfo så detektions-koden tror entry'en er
    krypteret — det rammer samme branch som ved en ægte krypteret zip
    fra macOS Finder/7-Zip/WinZip.
    """

    def test_kun_krypterede_entries_giver_password_besked(self, monkeypatch):
        # Lav en almindelig zip og monkey-patch infolist til at
        # returnere entries med flag_bits=1 (krypteret-bit sat).
        zip_bytes = _byg_simpel_zip({"hemmelig.pdf": b"data"})

        original_infolist = zipfile.ZipFile.infolist

        def faked_infolist(self):
            entries = original_infolist(self)
            for e in entries:
                e.flag_bits = e.flag_bits | 0x1
            return entries

        monkeypatch.setattr(zipfile.ZipFile, "infolist", faked_infolist)

        filer, fejl = udpak_zip_til_filer(zip_bytes)
        assert filer == []
        assert fejl is not None
        assert "adgangskode" in fejl.lower() or "password" in fejl.lower()
        # Skal vejlede brugeren konkret
        assert "manuelt" in fejl.lower() or "udpak" in fejl.lower() or "pak" in fejl.lower()


class TestTomZip:
    def test_zip_uden_filer_returnerer_tom_uden_fejl(self):
        # Zip med 0 filer er valid — bare ingen at udpakke
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w"):
            pass
        filer, fejl = udpak_zip_til_filer(buf.getvalue())
        assert filer == []
        assert fejl is None  # Ingen fejl, bare tom
