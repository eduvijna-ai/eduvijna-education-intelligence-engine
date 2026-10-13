from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from app.adapters.anythingllm.factory import build_anythingllm_adapter
from app.db.session import session_factory
from app.knowledge_intelligence.contracts import KnowledgeRetrievalRequest
from app.knowledge_intelligence.retrieval_profile import DEFAULT_RETRIEVAL_PROFILE_VERSION
from app.knowledge_intelligence.service import KnowledgeIntelligenceService


def main() -> None:
    parser = argparse.ArgumentParser(description="Knowledge Intelligence engineering CLI (D7-29)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("probe", help="Probe AnythingLLM gateway availability")

    index_parser = sub.add_parser("index", help="Index one eligible source revision")
    index_parser.add_argument("source_revision_id")
    index_parser.add_argument(
        "--profile-version",
        default=DEFAULT_RETRIEVAL_PROFILE_VERSION,
    )

    query_parser = sub.add_parser("query", help="Run scoped knowledge retrieval")
    query_parser.add_argument("query_text")
    query_parser.add_argument("--organization-id")
    query_parser.add_argument("--institution-id")
    query_parser.add_argument("--teacher-id")
    query_parser.add_argument("--top-k", type=int, default=5)
    query_parser.add_argument(
        "--profile-version",
        default=DEFAULT_RETRIEVAL_PROFILE_VERSION,
    )

    inspect_parser = sub.add_parser("inspect-binding", help="Inspect binding provenance")
    inspect_parser.add_argument("binding_id")

    retire_parser = sub.add_parser("retire-binding", help="Retire a knowledge binding")
    retire_parser.add_argument("binding_id")

    args = parser.parse_args()
    adapter = build_anythingllm_adapter(force_fake=True)
    session = session_factory()()
    try:
        service = KnowledgeIntelligenceService(session, adapter=adapter)
        if args.command == "probe":
            print(json.dumps(asdict(service.probe_gateway()), indent=2))
            return
        if args.command == "index":
            binding = service.index_source_revision(
                args.source_revision_id,
                retrieval_profile_version=args.profile_version,
            )
            session.commit()
            print(json.dumps(service.inspect_binding(binding.id), indent=2))
            return
        if args.command == "query":
            result = service.retrieve(
                KnowledgeRetrievalRequest(
                    query_text=args.query_text,
                    organization_id=args.organization_id,
                    institution_id=args.institution_id,
                    teacher_id=args.teacher_id,
                    top_k=args.top_k,
                    retrieval_profile_version=args.profile_version,
                )
            )
            pack = service.build_context_pack(result)
            session.commit()
            print(
                json.dumps(
                    {
                        "retrieval": result.model_dump(mode="json"),
                        "context_pack": pack.model_dump(mode="json"),
                    },
                    indent=2,
                )
            )
            return
        if args.command == "inspect-binding":
            print(json.dumps(service.inspect_binding(args.binding_id), indent=2))
            return
        if args.command == "retire-binding":
            binding = service.retire_binding(args.binding_id)
            session.commit()
            print(json.dumps(service.inspect_binding(binding.id), indent=2))
    finally:
        session.close()


if __name__ == "__main__":
    main()
