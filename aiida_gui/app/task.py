from .utils import get_node_summary_table, get_node_inputs, get_node_outputs
from aiida import orm
from fastapi import APIRouter, HTTPException
import traceback
from typing import List, Optional
from aiida.engine.processes import control
from pydantic import BaseModel

router = APIRouter()


class Task(BaseModel):
    """A task selected in the workflow editor, as sent by the frontend.

    `pk` is omitted (null) for tasks that have not run yet.
    """

    name: str = ""
    pk: Optional[int] = None


@router.get("/api/task/{id}/{path:path}")
async def read_task(id: int, path: str):
    from aiida.orm import load_node

    try:
        node = load_node(id)
        segments = path.split("/")
        if isinstance(node, orm.WorkChainNode):
            pk = int(segments[0].split("-")[-1])
            try:
                task_node = orm.load_node(pk)
            except Exception:
                raise HTTPException(status_code=404, detail=f"Process {pk} not found")

            # metadata = get_node_summary_table(node),
            # metadata["name"] = segments[0].split("_")[0]
            # metadata["node_type"] = node.node_type
            # metadata["identifier"] = "any"
            # try:
            #     executor = inspect.getsource(task_node.process_class)
            # except Exception:
            #     executor = f"{task_node.process_class.__module__}.{task_node.process_class.__name__}"
            executor = f"{task_node.process_class.__module__}.{task_node.process_class.__name__}"

            content = {
                "node_type": task_node.node_type,
                "label": segments[0].split("_")[0],
                "metadata": get_node_summary_table(task_node),
                "inputs": get_node_inputs(task_node),
                "outputs": get_node_outputs(task_node),
                "executor": executor,
                "process": {"pk": pk},
            }
        else:
            raise HTTPException(status_code=404, detail="Node not found")
        return content
    except KeyError as e:
        error_traceback = traceback.format_exc()  # Capture the full traceback
        print(error_traceback)
        raise HTTPException(
            status_code=404, detail=f"Process {id}/{path} not found, {e}"
        )


# General function to manage task actions
async def manage_task_action(action: str, id: int, tasks: List[Task]):

    node = orm.load_node(id)
    if not isinstance(node, orm.WorkChainNode):
        raise HTTPException(status_code=400, detail=f"Node {id} is not a workchain")
    if node.is_finished:
        raise HTTPException(status_code=400, detail="Process is finished.")
    if not tasks:
        raise HTTPException(status_code=400, detail="No tasks provided")
    pks = [task.pk for task in tasks if task.pk is not None]
    if not pks:
        raise HTTPException(
            status_code=400, detail="None of the selected tasks has a process"
        )
    try:
        processes = [orm.load_node(pk) for pk in pks]
    except Exception:
        raise HTTPException(status_code=404, detail=f"Tasks {pks} not found")
    for process in processes:
        if not isinstance(process, orm.ProcessNode):
            raise HTTPException(
                status_code=400, detail=f"Node {process.pk} is not a process"
            )
    actions = {
        "pause": (control.pause_processes, "Paused tasks"),
        "play": (control.play_processes, "Played tasks"),
        "kill": (control.kill_processes, "Killed tasks"),
    }
    if action not in actions:
        raise HTTPException(status_code=400, detail="Unsupported action")
    action_func, msg = actions[action]
    try:
        print(f"Performing '{action}' on processes {pks} in workchain {id}")
        action_func(processes, timeout=5)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": msg}


# Endpoint for pausing tasks in a process
@router.post("/api/process/tasks/pause/{id}")
async def pause_process_tasks(id: int, tasks: List[Task] = None):
    return await manage_task_action("pause", id, tasks or [])


# Endpoint for playing tasks in a process
@router.post("/api/process/tasks/play/{id}")
async def play_process_tasks(id: int, tasks: List[Task] = None):
    return await manage_task_action("play", id, tasks or [])


# Endpoint for killing tasks in a process
@router.post("/api/process/tasks/kill/{id}")
async def kill_workgraph_tasks(id: int, tasks: List[Task] = None):
    return await manage_task_action("kill", id, tasks or [])
