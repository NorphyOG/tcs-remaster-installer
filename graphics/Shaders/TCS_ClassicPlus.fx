// Original, self-contained ReShade FX shader. MIT License (see LICENSE).
// Post-processing only: no new textures, geometry, ray tracing or depth effects.
// Defaults deliberately mild to preserve the original presentation.
// Not GPU-compiled or visually tested with TCS in this environment.

uniform float SharpenAmount < ui_type = "slider"; ui_min = 0.0; ui_max = 0.5; ui_label = "Mild sharpening"; > = 0.12;
uniform float Saturation < ui_type = "slider"; ui_min = 0.8; ui_max = 1.2; ui_label = "Saturation"; > = 1.025;
uniform float Contrast < ui_type = "slider"; ui_min = 0.8; ui_max = 1.2; ui_label = "Contrast"; > = 1.015;

texture2D BackBuffer : COLOR;
sampler2D BackSampler { Texture = BackBuffer; };

void VS_Fullscreen(in uint id : SV_VertexID,
                   out float4 position : SV_Position,
                   out float2 uv : TEXCOORD0)
{
    uv.x = (id == 2) ? 2.0 : 0.0;
    uv.y = (id == 1) ? 2.0 : 0.0;
    position = float4(uv * float2(2.0, -2.0) + float2(-1.0, 1.0), 0.0, 1.0);
}

float4 PS_ClassicPlus(float4 position : SV_Position, float2 uv : TEXCOORD0) : SV_Target
{
    float2 pixel = float2(BUFFER_RCP_WIDTH, BUFFER_RCP_HEIGHT);
    float4 original = tex2D(BackSampler, uv);
    float3 left = tex2D(BackSampler, uv - float2(pixel.x, 0.0)).rgb;
    float3 right = tex2D(BackSampler, uv + float2(pixel.x, 0.0)).rgb;
    float3 up = tex2D(BackSampler, uv - float2(0.0, pixel.y)).rgb;
    float3 down = tex2D(BackSampler, uv + float2(0.0, pixel.y)).rgb;
    float3 localMin = min(original.rgb, min(min(left, right), min(up, down)));
    float3 localMax = max(original.rgb, max(max(left, right), max(up, down)));
    float3 sharpened = original.rgb + (original.rgb - (left + right + up + down) * 0.25) * SharpenAmount;
    float3 color = clamp(sharpened, localMin, localMax);
    float gray = dot(color, float3(0.2126, 0.7152, 0.0722));
    color = lerp(float3(gray, gray, gray), color, Saturation);
    color = (color - 0.5) * Contrast + 0.5;
    return float4(saturate(color), original.a);
}

technique TCS_ClassicPlus < ui_label = "TCS Classic Plus"; >
{
    pass
    {
        VertexShader = VS_Fullscreen;
        PixelShader = PS_ClassicPlus;
    }
}
