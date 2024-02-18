import json
from typing import Optional

from pydantic import BaseModel

from ..common.util import render_workflow_template
from ..common.config import C
from ..engine.params import GenerationParams, Constraint
from .model import Thinking, Generation, GenerationState

if 0:
    from ..workflow.model import Task


class VerifyPlanResponse(BaseModel):
    approve_changes: bool
    reasoning: str


VERIFY_PLAN_RESPONSE_SCHEMA = VerifyPlanResponse.model_json_schema()


class Planning(Thinking):

    async def run(self, task: 'Task', max_attempts: int = 10):
        from ..workflow.model import TaskState

        previous_plan_gen: Optional[Generation] = None

        for attempt in range(max_attempts):
            instruction = render_workflow_template(
                'plan',
                task=task,
            )
            params = GenerationParams(n=16, beam_search=True, max_tokens=1000, temperature=0.7)
            plan_gen = Generation.new('plan', C.SYSTEM_CODING_ASSISTANT, instruction, params)

            if previous_plan_gen is not None:
                self.retry(previous_plan_gen, plan_gen)
            else:
                self.start(plan_gen)
            previous_plan_gen = plan_gen

            await self.wait_for_generations()
            if plan_gen.state != GenerationState.COMPLETED:
                task.state = TaskState.FAILED
                task.error = 'Planning generation failed'
                return

            for plan_index, completion in enumerate(plan_gen.completions):

                instruction = render_workflow_template(
                    'verify_plan',
                    task=task,
                    schema=VERIFY_PLAN_RESPONSE_SCHEMA,
                    proposed_code_changes=completion
                )

                constraint = Constraint.from_json_schema(VERIFY_PLAN_RESPONSE_SCHEMA)
                params = GenerationParams(n=16, beam_search=True, max_tokens=500, temperature=0.5, constraint=constraint)
                verify_gen = Generation.new('verify_plan', C.SYSTEM_CODING_ASSISTANT, instruction, params)
                self.verify(verify_gen, plan_gen)
                await self.wait_for_generations()
                if verify_gen.state != GenerationState.COMPLETED:
                    task.state = TaskState.FAILED
                    task.error = f'Plan verification generation failed: {verify_gen.error}'
                    return

                vote = sum(json.loads(response)['approve_changes'] for response in verify_gen.completions)
                if vote >= (params.n + 1) // 2:
                    task.plan = completion
                    self.concluding_id = plan_gen.id
                    self.concluding_index = plan_index
                    return

        task.state = TaskState.FAILED
        task.error = 'Failed to plan code changes (max attempts)'
