import numpy as np

from bcf.v3.bcfxml import BcfXml
import bcf.v3.visinfo as visinfo
from bcf.v3.model import ComponentColoring, ComponentColoringColor, ComponentColoringColorComponents, VisualizationInfo
import ifcopenshell
from clash import ClashReport

class BCFExporter:
    def __init__(self, clash_report: ClashReport, ifc_path: str | None = None):
        self.clash_report = clash_report
        self.ifc_model = ifcopenshell.open(ifc_path) if ifc_path else None

    def export(self, output_file="clash_report.bcfzip"):
        report_data = self.clash_report.generate_report()
        if not report_data:
            raise ValueError("Nenhum dado de conflito encontrado para exportar.")

        bcf = BcfXml.create_new("Clash Report Export")
        bcf.project.name = "Clash Report Export"

        for clash in report_data:
            severity = clash.get("automatedAnalysis", {}).get("severity", 0)
            title = (
                f"Clash {clash.get('id','')} : "
                f"{clash.get('disciplines',['?','?'])[0]} x {clash.get('disciplines',['?','?'])[1]}"
            )

            topic = bcf.add_topic(
                title=title,
                description=self._build_description(clash),
                author="Clash Analyzer",
                topic_type="Clash",
                topic_status="Open",
            )

            identifier = clash.get("identifier", "ElementID")
            items = clash.get("items", [])
            location = clash.get("location", [0.0, 0.0, 0.0])

            guids = []
            for item in items:
                if isinstance(item, str) and item.startswith("GUID:"):
                    guids.append(item.replace("GUID:", ""))
                elif isinstance(item, (int, str)) and identifier.lower() == "elementid" and self.ifc_model:
                    g = self._find_guid_by_element_id(item)
                    guids.append(g or str(item))
                else:
                    guids.append(str(item))

            try:
                pos_arr = np.asarray(location, dtype=float)
                vp_handler = topic.add_viewpoint_from_point_and_guids(pos_arr, *guids) if guids else topic.add_viewpoint_from_point_and_guids(pos_arr)

                if vp_handler is None:
                    vis = visinfo.build_viewpoint_from_position_and_guids(pos_arr, *guids) if guids else visinfo.build_viewpoint_from_position_and_guids(pos_arr)
                    vp_handler = visinfo.VisualizationInfoHandler(vis, xml_handler=bcf._xml_handler)
                    topic.add_visinfo_handler(vp_handler)

                cam_pos = np.asarray(location, dtype=float)
                cam_dir = np.array([0.0, 0.0, -1.0])
                cam_up = np.array([0.0, 1.0, 0.0])
                vp_handler.visualization_info.perspective_camera = visinfo.build_camera_from_vectors(cam_pos, cam_dir, cam_up)

                if guids:
                    comps = visinfo.build_components(*guids)
                    vp_handler.visualization_info.components = comps

                    try:
                        color_hex = self._severity_to_color(severity)
                        ccc = ComponentColoringColorComponents(components=[c.Guid for c in comps.components]) if hasattr(comps, 'components') else None
                        if ccc:
                            cc = ComponentColoring(
                                color=ComponentColoringColor(
                                    r=int(color_hex[1:3], 16),
                                    g=int(color_hex[3:5], 16),
                                    b=int(color_hex[5:7], 16)
                                ),
                                components=ccc
                            )
                            vis_info = vp_handler.visualization_info
                            existing = getattr(vis_info, "component_colorings", None) or []
                            existing.append(cc)
                            vis_info.component_colorings = existing
                    except Exception:
                        pass

                if self.ifc_model and guids:
                    elems = []
                    for g in guids:
                        try:
                            e = self.ifc_model.by_guid(g)
                            if e:
                                elems.append(e)
                        except Exception:
                            pass
                    if elems:
                        vp_handler.set_selected_elements(elems)
                        vp_handler.set_visible_elements(elems)

            except Exception as e:
                print(f"Erro ao criar viewpoint/visualization para topic {title}: {e}")

        bcf.save(output_file)
        print(f"✅ Arquivo BCF exportado com sucesso: {output_file}")

    def _find_guid_by_element_id(self, element_id):
        if not self.ifc_model:
            return None
        try:
            for elem in self.ifc_model.by_type("IfcElement"):
                for pset in getattr(elem, "IsDefinedBy", []) or []:
                    prop = getattr(pset, "RelatingPropertyDefinition", None)
                    if prop and hasattr(prop, "HasProperties"):
                        for p in getattr(prop, "HasProperties", []) or []:
                            name = getattr(p, "Name", "")
                            if not name:
                                continue
                            if name.lower() in ["elementid", "revit_id", "id"]:
                                val = None
                                if hasattr(p, "NominalValue") and getattr(p.NominalValue, "wrappedValue", None) is not None:
                                    val = p.NominalValue.wrappedValue
                                elif hasattr(p, "Value") and getattr(p.Value, "wrappedValue", None) is not None:
                                    val = p.Value.wrappedValue
                                if val is not None and str(val) == str(element_id):
                                    return elem.GlobalId
        except Exception:
            pass
        return None

    def _build_description(self, clash):
        severity = clash.get("automatedAnalysis", {}).get("severity", 0)
        lines = [
            f"Fonte: {clash.get('sourceFile','')}",
            f"Tipo: {clash.get('clashType','')}",
            f"Distância: {clash.get('distance','')} m",
            f"Severidade: {severity}",
            f"Custo Rework: {clash.get('automatedAnalysis',{}).get('reworkCost','')}",
            "Itens detalhados:",
        ]
        items_info = clash.get("itemsInfo", {})
        for key in ["first", "second"]:
            info = items_info.get(key, {})
            lines.append(
                f"- {key}: {info.get('discipline','')} | {info.get('category','')} | "
                f"{info.get('name','')} | {info.get('volume','')} | "
                f"{info.get('surface_area','')} | {info.get('weight_kg','')}"
            )
        return "\n".join(lines)

    def _severity_to_color(self, severity: float):
        s = max(0, min(100, float(severity))) / 100.0
        r = int(255 * s)
        g = int(255 * (1 - s))
        b = 0
        return f"#{r:02X}{g:02X}{b:02X}"

    def _severity_to_priority(self, severity: float):
        if severity >= 75:
            return "Highest"
        elif severity >= 50:
            return "High"
        elif severity >= 25:
            return "Medium"
        return "Low"
