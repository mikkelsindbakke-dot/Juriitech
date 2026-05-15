/**
 * Klient-side ZIP-udpakning.
 *
 * Når brugeren uploader en ZIP-fil, pakker vi den ud direkte i browseren
 * så hver fil inde i zippen vises individuelt i Sagsakter-sektionen,
 * Anonymisér-sektionen osv. — præcis som hvis filerne var uploadet
 * enkeltvis. Backend ser også en flad fil-liste (zip-udpakningen sker
 * i FastAPI's _laes_uploads_med_zip_udpakning), men UI'et havde
 * historisk vist zippen som ÉN entry og brugeren skulle uploade hver
 * fil manuelt for at få korrekt liste.
 *
 * Beslutninger:
 *   - Skipper __MACOSX/ og skjulte filer (starter med ".") — samme
 *     regler som backend's udpak_zip_til_filer.
 *   - Skipper video/lyd-filer (mp4/mov/mp3/m4a/wav/...) inden de når
 *     backend. Backend håndterer kun .mp4 specifikt; andre medie-typer
 *     ville få "fil_ikke_laest"-fejl. Vi rapporterer dem til UI'et så
 *     brugeren får en venlig besked.
 *   - Flader sti-prefiks: 'mappe/fil.pdf' → 'fil.pdf' (også backend-
 *     adfærd).
 *   - Kun læsbare zip-entries — krypterede/ødelagte zips returneres
 *     som fejl med konkret handling i UI'et.
 */
import JSZip from "jszip";

const MEDIA_EXTENSIONS = new Set([
  // Video
  "mp4",
  "mov",
  "avi",
  "mkv",
  "webm",
  "wmv",
  "flv",
  "m4v",
  // Audio
  "mp3",
  "wav",
  "m4a",
  "ogg",
  "flac",
  "aac",
  "wma",
  "opus",
]);

function erMediaFil(navn: string): boolean {
  const ext = navn.split(".").pop()?.toLowerCase();
  return ext != null && MEDIA_EXTENSIONS.has(ext);
}

function erSkraldEntry(stiInZip: string): boolean {
  // __MACOSX-skrald og skjulte filer (starter med .) — på alle niveauer
  // af stien.
  if (stiInZip.startsWith("__MACOSX/")) return true;
  const segments = stiInZip.split("/");
  const sidste = segments[segments.length - 1];
  if (sidste === "" || sidste.startsWith(".")) return true;
  return false;
}

export interface ZipFejl {
  filnavn: string;
  besked: string;
}

export interface UdpakningsResultat {
  filer: File[];
  skipped_media: string[];
  fejl: ZipFejl[];
}

async function udpak_én_zip(
  zipFil: File,
): Promise<{ filer: File[]; skipped_media: string[]; fejl: ZipFejl | null }> {
  const filer: File[] = [];
  const skipped_media: string[] = [];

  let zip: JSZip;
  try {
    zip = await JSZip.loadAsync(await zipFil.arrayBuffer());
  } catch (e) {
    return {
      filer: [],
      skipped_media: [],
      fejl: {
        filnavn: zipFil.name,
        besked:
          e instanceof Error && /encrypted|password/i.test(e.message)
            ? "Zip-filen er beskyttet med adgangskode. Pak den ud manuelt på din computer og upload filerne enkeltvis."
            : "Zip-filen er ødelagt eller bruger et kompressionsformat vi ikke understøtter. Pak den ud manuelt og upload filerne enkeltvis.",
      },
    };
  }

  // jszip giver os alle entries — både filer og mapper (mapper har
  // entry.dir === true). Vi vil kun have rigtige filer.
  const entries = Object.entries(zip.files).filter(
    ([, entry]) => !entry.dir,
  );

  for (const [stiInZip, entry] of entries) {
    if (erSkraldEntry(stiInZip)) continue;
    const kortNavn = stiInZip.split("/").pop() ?? stiInZip;
    if (!kortNavn || kortNavn.startsWith(".")) continue;

    if (erMediaFil(kortNavn)) {
      skipped_media.push(kortNavn);
      continue;
    }

    try {
      const blob = await entry.async("blob");
      filer.push(new File([blob], kortNavn));
    } catch {
      // Enkelt-entry kunne ikke læses (krypteret indlejret fil osv.).
      // Vi behandler det som skipped frem for hård-fejl — brugeren får
      // resten af zippen alligevel.
      skipped_media.push(kortNavn);
    }
  }

  return { filer, skipped_media, fejl: null };
}

/**
 * Pakker alle .zip-filer ud klient-side og returnerer en flad liste af
 * File-objekter til upload. Ikke-zip-filer passerer uændret.
 *
 * @param input Filer brugeren har valgt (kan være en blanding af zip og
 *   enkelte filer).
 * @returns Flad liste + lister over skippede medie-filer og zip-fejl
 *   som UI'et kan vise til brugeren.
 */
export async function udpak_zips_klient(
  input: File[],
): Promise<UdpakningsResultat> {
  const filer: File[] = [];
  const skipped_media: string[] = [];
  const fejl: ZipFejl[] = [];

  for (const fil of input) {
    if (!fil.name.toLowerCase().endsWith(".zip")) {
      filer.push(fil);
      continue;
    }
    const r = await udpak_én_zip(fil);
    if (r.fejl) {
      fejl.push(r.fejl);
      continue;
    }
    filer.push(...r.filer);
    skipped_media.push(...r.skipped_media);
  }

  return { filer, skipped_media, fejl };
}
