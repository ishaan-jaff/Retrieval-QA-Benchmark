from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Extra

from retrieval_qa_benchmark.schema import (
    BaseDataset,
    BaseEvaluator,
    BaseLLM,
    BaseTransform,
    TransformGraph,
)
from retrieval_qa_benchmark.utils.registry import REGISTRY


class BaseFactory(BaseModel):
    """ """

    type: str
    args: Optional[Dict[str, Any]] = {}
    run_args: Optional[Dict[str, Any]] = {}

    class Config:
        extra = Extra.ignore

    @classmethod
    def from_config(cls, config: Dict[str, Any], **kwargs: Any) -> BaseFactory:
        type = config["type"]
        args = config["args"] if "args" in config else {}
        run_args = config["run_args"] if "run_args" in config else {}
        return cls(type=type, args=args, run_args=run_args)

    def build(self) -> Any:
        raise NotImplementedError


class DatasetFactory(BaseFactory):
    """ """

    def build(self) -> BaseDataset:
        return REGISTRY.Datasets[self.type].build(**self.args)


class TransformFactory(BaseFactory):
    """ """

    id: str = "default"

    @classmethod
    def from_config(
        cls, config: Dict[str, Any], id: str = "default", **kwargs: Any
    ) -> BaseFactory:
        type = config["type"]
        args = config["args"] if "args" in config else {}
        run_args = config["run_args"] if "run_args" in config else {}
        return cls(id=id, type=type, args=args, run_args=run_args)

    def build(self) -> BaseTransform:
        return REGISTRY.Transforms[self.type](**self.args)


class TransformGraphFactory(BaseModel):
    nodes_config: Dict[str, Any] = {}

    def build(self) -> TransformGraph:
        if "nodes" in self.nodes_config and len(self.nodes_config["nodes"]) > 0:
            nodes_config = self.nodes_config["nodes"]
            if type(nodes_config) in [list, tuple]:
                entry_id = "0"
                transforms = {
                    str(i): TransformFactory.from_config(c, id=str(i)).build()
                    for i, c in enumerate(nodes_config)
                }
                for i in range(len(nodes_config)):
                    if i > 0:
                        transforms[str(i - 1)].children = [
                            transforms[str(i)],
                            transforms[str(i)],
                        ]
            else:
                entry_id = self.nodes_config["entry_id"]
                transforms = {
                    k: TransformFactory.from_config(c, id=k).build()
                    for k, c in nodes_config.items()
                }
                for k, c in nodes_config.items():
                    transforms[k].children = [
                        transforms[i] if i is not None else None for i in c["next"]
                    ]
            assert (
                entry_id != ""
            ), "Entry ID must not be empty for dictionary of transforms"
            assert (
                entry_id in transforms
            ), "Entry ID must be in keys of transform dictionary"
        else:
            entry_id = ""
            transforms = {}
        return TransformGraph(entry_id=entry_id, nodes=transforms)


class ModelFactory(BaseFactory):
    """ """

    def build(self) -> BaseLLM:
        return REGISTRY.LLMs[self.type].build(**self.args, run_args=self.run_args)


class EvaluatorFactory(BaseFactory):
    """Evaluator Factory"""

    config: Dict[str, Any]

    @classmethod
    def from_config(cls, config: Dict[str, Any], **kwargs: Any) -> BaseFactory:
        config_ = config["evaluator"]
        type = config_["type"]
        return cls(config=config_, type=type)

    def build(self) -> BaseEvaluator:
        if type(self.config["dataset"]) is list:
            dataset = DatasetFactory.from_config(self.config["dataset"][0]).build()
            for c in self.config["dataset"][1:]:
                dataset += DatasetFactory.from_config(c).build()
        else:
            dataset = DatasetFactory.from_config(self.config["dataset"]).build()
        if "transform" in self.config:
            transform = TransformGraphFactory(
                nodes_config=self.config["transform"]
            ).build()
        else:
            transform = TransformGraphFactory(nodes_config={}).build()
        model = ModelFactory.from_config(self.config["model"]).build()
        out_file = self.config["out_file"] if "out_file" in self.config else None
        return REGISTRY.Evaluators[self.type](
            dataset=dataset, transform=transform, llm=model, out_file=out_file
        )
