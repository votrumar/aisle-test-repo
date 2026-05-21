from lxml import etree


def sensor_to_xml(name: str, location: str) -> bytes:
    root = etree.Element("sensor")
    root.set("name", name)
    root.set("location", location)
    return etree.tostring(root, encoding="utf-8", xml_declaration=True)


def parse_sensor_xml(xml_bytes: bytes) -> dict[str, str]:
    parser = etree.XMLParser(
        no_network=True,
        resolve_entities=False,
        dtd_validation=False,
        load_dtd=False,
    )
    tree = etree.fromstring(xml_bytes, parser)
    name = tree.get("name")
    location = tree.get("location")
    if name is None or location is None:
        raise ValueError("xml is missing required attributes: name, location")
    return {"name": name, "location": location}
