from src.services.pipeline_runner import (  # project pipeline runner
    PipelineRequest,
    run_clipforge_pipeline
)

request = PipelineRequest(
    input_video=r"H:\Haseeb\Code With Harry\AI_Content_Bot_Project_Plan\ClipForge AI\data\input\what is pain sad multifandom.mp4",
    platform="youtube",
    aspect_ratio="9:16",
    segment_mode="semantic_ai",
    captions=True,
)

result = run_clipforge_pipeline(request)

print(result)
