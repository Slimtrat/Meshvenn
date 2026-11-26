"""World-space woven detail; authored material, never source-observed texture."""


def procedural_detail(material, base_color, config):
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    def math_node(operation, a, b=None):
        n = nodes.new("ShaderNodeMath")
        n.operation = operation
        for i, value in enumerate((a, b)):
            if value is None:
                continue
            if isinstance(value, (int, float)):
                n.inputs[i].default_value = value
            else:
                links.new(value, n.inputs[i])
        return n.outputs[0]

    geometry = nodes.new("ShaderNodeNewGeometry")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1 / config.thread_spacing
    noise.inputs["Detail"].default_value = 2.0
    links.new(geometry.outputs["Position"], noise.inputs["Vector"])
    separate = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geometry.outputs["Position"], separate.inputs[0])
    waves = []
    for component in separate.outputs:
        waves.append(
            math_node(
                "SINE",
                math_node(
                    "MULTIPLY",
                    component,
                    2 * __import__("math").pi / config.thread_spacing,
                ),
            )
        )
    normal_abs = nodes.new("ShaderNodeVectorMath")
    normal_abs.operation = "ABSOLUTE"
    links.new(geometry.outputs["Normal"], normal_abs.inputs[0])
    normal = nodes.new("ShaderNodeSeparateXYZ")
    links.new(normal_abs.outputs["Vector"], normal.inputs[0])
    weights = [math_node("POWER", s, 4.0) for s in normal.outputs]
    denominator = math_node(
        "MAXIMUM",
        math_node("ADD", math_node("ADD", weights[0], weights[1]), weights[2]),
        1e-6,
    )
    heights = [
        math_node("ADD", waves[1], waves[2]),
        math_node("ADD", waves[0], waves[2]),
        math_node("ADD", waves[0], waves[1]),
    ]
    weighted = [math_node("MULTIPLY", h, w) for h, w in zip(heights, weights)]
    weave = math_node(
        "DIVIDE",
        math_node("ADD", math_node("ADD", weighted[0], weighted[1]), weighted[2]),
        denominator,
    )
    luminance = nodes.new("ShaderNodeRGBToBW")
    links.new(base_color, luminance.inputs[0])
    mask = nodes.new("ShaderNodeMapRange")
    mask.clamp = True
    links.new(luminance.outputs[0], mask.inputs["Value"])
    mask.inputs["From Min"].default_value = 0.10
    mask.inputs["From Max"].default_value = 0.30
    # Dark painted buttons receive less cloth grain and a smoother finish.
    height = math_node(
        "MULTIPLY",
        math_node(
            "ADD",
            math_node("MULTIPLY", weave, 0.35),
            math_node("MULTIPLY", noise.outputs["Fac"], 0.3),
        ),
        mask.outputs[0],
    )
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 1.0
    bump.inputs["Distance"].default_value = config.relief
    links.new(height, bump.inputs["Height"])
    variation = math_node(
        "ADD",
        config.roughness - 0.03,
        math_node("MULTIPLY", noise.outputs["Fac"], 0.06),
    )
    rough = math_node(
        "ADD",
        config.button_roughness,
        math_node(
            "MULTIPLY",
            mask.outputs[0],
            math_node("SUBTRACT", variation, config.button_roughness),
        ),
    )
    return bump.outputs["Normal"], rough


def portable_images(material, shader, uv_name, normal, roughness):
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = uv_name

    def image_node(image):
        n = nodes.new("ShaderNodeTexImage")
        n.image = image
        n.interpolation = "Linear"
        links.new(uv.outputs["UV"], n.inputs["Vector"])
        return n

    tangent = nodes.new("ShaderNodeNormalMap")
    tangent.space = "TANGENT"
    tangent.uv_map = uv_name
    links.new(image_node(normal).outputs["Color"], tangent.inputs["Color"])
    links.new(tangent.outputs["Normal"], shader.inputs["Normal"])
    separate = nodes.new("ShaderNodeSeparateColor")
    separate.mode = "RGB"
    links.new(image_node(roughness).outputs["Color"], separate.inputs["Color"])
    links.new(separate.outputs["Green"], shader.inputs["Roughness"])
    links.new(separate.outputs["Blue"], shader.inputs["Metallic"])
