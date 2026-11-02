"""Lectura de RSS: XML, limpieza de HTML, fechas en UTC e identificador de noticia."""

import hashlib
import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from lxml import etree

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)


def parsear_xml(contenido):
    """Devuelve la raíz del XML o lanza XMLSyntaxError si está malformado."""
    return etree.fromstring(contenido, _PARSER)


def items_de(contenido):
    raiz = parsear_xml(contenido)
    items = []
    for nodo in raiz.iter("item"):
        def texto(etiqueta):
            elemento = nodo.find(etiqueta)
            return (elemento.text or "").strip() if elemento is not None else ""

        items.append({
            "guid": texto("guid"),
            "titulo": texto("title"),
            "enlace": texto("link"),
            "descripcion": texto("description"),
            "fecha": texto("pubDate"),
            "categoria": texto("category"),
        })
    return items


def limpiar_html(texto):
    if not texto:
        return ""
    texto = html.unescape(texto)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = html.unescape(texto)
    return re.sub(r"\s+", " ", texto).strip()


def a_utc(texto):
    """Convierte la fecha del RSS a UTC sin zona. Devuelve None si no se puede interpretar."""
    if not texto:
        return None
    try:
        if "T" in texto:
            momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        else:
            momento = parsedate_to_datetime(texto)
    except (ValueError, TypeError):
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc).replace(tzinfo=None)


def enlace_valido(enlace):
    partes = urlparse(enlace or "")
    return partes.scheme in ("http", "https") and bool(partes.netloc)


def id_noticia(guid, enlace):
    """El guid si existe; si no, el hash del enlace. None si no hay ninguno de los dos."""
    if guid:
        return guid
    if enlace:
        return "enlace-" + hashlib.sha256(enlace.encode("utf-8")).hexdigest()[:32]
    return None


def hash_texto(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def hash_contenido(titulo, descripcion):
    return hash_texto(f"{titulo}\n{descripcion}")
