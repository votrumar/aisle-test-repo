from lxml import etree


def sensor_to_xml(name: str, location: str) -> bytes:
    root = etree.Element("sensor")
    root.set("name", name)
    root.set("location", location)
    return etree.tostring(root, encoding="utf-8", xml_declaration=True)
