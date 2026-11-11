import logging
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_experimental.graph_transformers.diffbot import DiffbotGraphTransformer
from langchain_neo4j import LLMGraphTransformer
from langchain_neo4j.graphs.graph_document import Relationship
from langchain_experimental.graph_transformers.llm import _Graph
# from src.shared.diffbot import DiffbotGraphTransformer, Graph
# from src.shared.diffbot import Graph
from langchain_anthropic import ChatAnthropic
from langchain_fireworks import ChatFireworks
from langchain_aws import ChatBedrock
from langchain_ollama import ChatOllama
import boto3
import google.auth
from src.shared.constants import ADDITIONAL_INSTRUCTIONS
from src.shared.llm_graph_builder_exception import LLMGraphBuilderException
import re
from langchain_core.callbacks.manager import CallbackManager
from src.shared.common_fn import UniversalTokenUsageHandler,get_value_from_env

def get_llm(model: str):
    """Retrieve the specified language model based on the model name."""
    model = model.upper().replace('.', '_').strip()
    env_key = f"LLM_MODEL_CONFIG_{model}"
    env_value = get_value_from_env(env_key)

    if not env_value:
        err = f"Environment variable '{env_key}' is not defined as per format or missing"
        logging.error(err)
        raise Exception(err)
    
    logging.info("Model: {}".format(env_key))
    callback_handler = UniversalTokenUsageHandler()
    callback_manager = CallbackManager([callback_handler])
    try:
        if "GEMINI" in model:
            model_name = env_value
            credentials, project_id = google.auth.default()
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                vertexai=True,
                credentials=credentials,
                project=project_id,
                temperature=0,
                callbacks=callback_manager,
                safety_settings={
                    "HARM_CATEGORY_UNSPECIFIED": "BLOCK_NONE",
                    "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
                    "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                    "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                },
            
            )
        elif "OPENAI" in model:
            model_name, api_key = env_value.split(",")
            llm= ChatOpenAI(
            api_key=api_key,
            model=model_name,
            callbacks=callback_manager,
            )

        elif "AZURE" in model:
            model_name, api_endpoint, api_key, api_version = env_value.split(",")
            llm = AzureChatOpenAI(
                api_key=api_key,
                azure_endpoint=api_endpoint,
                azure_deployment=model_name,  # takes precedence over model parameter
                api_version=api_version,
                temperature=0,
                max_tokens=None,
                timeout=None,
                callbacks=callback_manager,
            )

        elif "ANTHROPIC" in model:
            model_name, api_key = env_value.split(",")
            anthropic_kwargs = {
                "api_key": api_key,
                "model": model_name,
                "base_url": os.getenv(
                    "ANTHROPIC_BASE_URL",
                    "https://api.anthropic.com",
                ),
                "timeout": None,
                "callbacks": callback_manager,
            }
            llm = ChatAnthropic(**anthropic_kwargs)

        elif "FIREWORKS" in model:
            model_name, api_key = env_value.split(",")
            llm = ChatFireworks(api_key=api_key, model=model_name,callbacks=callback_manager)

        elif "GROQ" in model:
            model_name, base_url, api_key = env_value.split(",")
            llm = ChatGroq(api_key=api_key, model_name=model_name, temperature=0,callbacks=callback_manager)

        elif "BEDROCK" in model:
            model_name, aws_access_key, aws_secret_key, region_name = env_value.split(",")
            bedrock_client = boto3.client(
                service_name="bedrock-runtime",
                region_name=region_name,
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
            )

            llm = ChatBedrock(
                client=bedrock_client,region_name=region_name, model_id=model_name, model_kwargs=dict(temperature=0),callbacks=callback_manager, 
            )

        elif "OLLAMA" in model:
            model_name, base_url = env_value.split(",")
            llm = ChatOllama(base_url=base_url, model=model_name,callbacks=callback_manager)

        elif "DIFFBOT" in model:
            #model_name = "diffbot"
            model_name, api_key = env_value.split(",")
            llm = DiffbotGraphTransformer(
                diffbot_api_key=api_key,
                extract_types=["entities", "facts"],
            )
            callback_handler = None
        
        else: 
            model_name, api_endpoint, api_key = env_value.split(",")
            llm = ChatOpenAI(
                api_key=api_key,
                base_url=api_endpoint,
                model=model_name,
                temperature=0,
                callbacks=callback_manager,
            )
    except Exception as e:
        err = f"Error while creating LLM '{model}': {str(e)}"
        logging.error(err)
        raise Exception(err)
    logging.info(f"Model created - Model Version: {model_name or ''}")
    return llm, model_name or "", callback_handler

def get_llm_model_name(llm):
    """Extract name of llm model from llm object"""
    for attr in ["model_name", "model", "model_id"]:
        model_name = getattr(llm, attr, None)
        if model_name:
            return model_name.lower()
    logging.info("Could not determine model name; defaulting to empty string")
    return ""

def get_combined_chunks(chunkId_chunkDoc_list, chunks_to_combine):
    combined_chunk_document_list = []
    combined_chunks_page_content = [
        "".join(
            document["chunk_doc"].page_content
            for document in chunkId_chunkDoc_list[i : i + chunks_to_combine]
        )
        for i in range(0, len(chunkId_chunkDoc_list), chunks_to_combine)
    ]
    combined_chunks_ids = [
        [
            document["chunk_id"]
            for document in chunkId_chunkDoc_list[i : i + chunks_to_combine]
        ]
        for i in range(0, len(chunkId_chunkDoc_list), chunks_to_combine)
    ]

    for i in range(len(combined_chunks_page_content)):
        combined_chunk_document_list.append(
            Document(
                page_content=combined_chunks_page_content[i],
                metadata={"combined_chunk_ids": combined_chunks_ids[i]},
            )
        )
    return combined_chunk_document_list

def get_chunk_id_as_doc_metadata(chunkId_chunkDoc_list):
    combined_chunk_document_list = [
       Document(
           page_content=document["chunk_doc"].page_content,
           metadata={"chunk_id": [document["chunk_id"]]},
       )
       for document in chunkId_chunkDoc_list
   ]
    return combined_chunk_document_list
      

async def get_graph_document_list(
    llm, combined_chunk_document_list, allowedNodes, allowedRelationship, callback_handler,
    additional_instructions=None, node_properties=None, relationship_properties=None,
    yaml_context=None,
):
    graph_document_list = []
    token_usage = 0
    try:
        if "diffbot_api_key" in dir(llm):
            llm_transformer = llm
        else:
            try:
                llm.with_structured_output(_Graph)
                supports_structured_output = True
            except Exception:
                supports_structured_output = False
            if supports_structured_output and not isinstance(llm, ChatGroq):
                logging.info("LLM supports structured output; including descriptions in graph")
                node_properties = list(node_properties or ["description"])
                relationship_properties = list(relationship_properties or ["description"])
                ignore_tool_usage = False
            else:
                logging.info("LLM does not support structured output; excluding descriptions in graph") 
                node_properties = False
                relationship_properties = False
                ignore_tool_usage = True
            
            transformer_instructions = build_transformer_instructions(
                additional_instructions, yaml_context
            )
            strict_mode = os.getenv("ONTOLOGY_STRICT_MODE", "true").strip().lower() not in {"0", "false", "no", "off"}
            logging.info("Ontology transformer strict_mode=%s; allowed relationship labels=%s", strict_mode, [item if isinstance(item, str) else item[1] for item in (allowedRelationship or [])])

            llm_transformer = LLMGraphTransformer(
                llm=llm,
                node_properties=node_properties,
                relationship_properties=relationship_properties,
                allowed_nodes=allowedNodes,
                allowed_relationships=allowedRelationship,
                ignore_tool_usage=ignore_tool_usage,
                strict_mode=strict_mode,
                additional_instructions=transformer_instructions
            )
        
        if isinstance(llm,DiffbotGraphTransformer):
            graph_document_list = llm_transformer.convert_to_graph_documents(combined_chunk_document_list)
        else:
            graph_document_list = await llm_transformer.aconvert_to_graph_documents(combined_chunk_document_list)
        for index, document in enumerate(graph_document_list):
            nodes = list(getattr(document, "nodes", ()) or ())
            relationships = list(getattr(document, "relationships", ()) or ())
            logging.info("LLM graph document %d: nodes=%d relationships=%d node_items=%s relationship_items=%s", index, len(nodes), len(relationships), [(str(getattr(node, "id", "")), str(getattr(node, "type", ""))) for node in nodes], [(str(getattr(getattr(rel, "source", None), "id", "")), str(getattr(rel, "type", "")), str(getattr(getattr(rel, "target", None), "id", ""))) for rel in relationships])
    except Exception as e:
       logging.error(f"Error in graph transformation: {e}", exc_info=True)
       raise LLMGraphBuilderException(f"Graph transformation failed: {str(e)}")
    finally:
        try:
            if callback_handler:
                usage = callback_handler.report()
                token_usage = usage.get("total_tokens", 0)
        except Exception as usage_err:
            logging.error(f"Error while reporting token usage: {usage_err}")

    return graph_document_list, token_usage


def build_transformer_instructions(user_instructions=None, yaml_context=None):
    """Build instructions while preserving YAML and sanitizing user text only."""
    instructions = ADDITIONAL_INSTRUCTIONS
    if yaml_context:
        ontology_rules = (
            "Ontology YAML is the source of truth. Use only classes and relationships "
            "defined in these profiles; do not invent ontology terms. "
            "Create a relationship only when the source entity type is in the "
            "relationship's domain and the target entity type is in its range."
        )
        instructions += "\n\n" + ontology_rules.replace("{", "[").replace("}", "]")
        instructions += "\n\n" + yaml_context.replace("{", "[").replace("}", "]")
    if user_instructions:
        instructions += "\n\nAdditional extraction instructions:\n" + sanitize_additional_instruction(user_instructions)
    return instructions


def rewrite_inverse_relationships(graph_documents, inverse_relationships):
    """Normalize extracted inverse predicates to the prompt's canonical form."""
    def normalize(value):
        return " ".join(str(value).replace("_", " ").casefold().split())

    inverse_map = {normalize(source): target for source, target in (inverse_relationships or ())}
    if not inverse_map:
        return graph_documents
    for document in graph_documents:
        rewritten = []
        for relationship in getattr(document, "relationships", ()) or ():
            kept = inverse_map.get(normalize(getattr(relationship, "type", "")))
            if kept is None:
                rewritten.append(relationship)
                continue
            rewritten.append(Relationship(
                source=relationship.target,
                target=relationship.source,
                type=kept,
                properties=getattr(relationship, "properties", None) or {},
            ))
        document.relationships = rewritten
    return graph_documents

async def get_graph_from_llm(model, chunkId_chunkDoc_list, allowedNodes, allowedRelationship, chunks_to_combine, additional_instructions=None, return_envelope=False):
   try:
       llm, model_name,callback_handler = get_llm(model)
       logging.info(f"Using model: {model_name}")
    
       combined_chunk_document_list = get_combined_chunks(chunkId_chunkDoc_list, chunks_to_combine)
       logging.info(f"Combined {len(combined_chunk_document_list)} chunks")
    
       ontology_profile = None
       if get_value_from_env("ONTOLOGY_GUIDED_EXTRACTION", "false", "bool") or get_value_from_env("ONTOLOGY_ONLY_MODE", "false", "bool"):
           from src.ontology_registry import OntologyExtractionAdapter, default_profile
           if get_value_from_env("ONTOLOGY_AUTO_PROFILE_SELECTION", "true", "bool"):
               from src.ontology_registry.profile_selector import select_profiles
               sample_limit = int(get_value_from_env("ONTOLOGY_PROFILE_SELECTION_MAX_CHARS", "24000"))
               document_sample = "\n\n".join(doc.page_content for doc in combined_chunk_document_list)
               selection = await select_profiles(llm, document_sample[:sample_limit])
               manifest = os.getenv(
                   "ONTOLOGY_MANIFEST_PATH",
                   os.path.join(os.path.dirname(__file__), "Ontology", "manifest.yaml"),
               )
               context_limit = os.getenv("ONTOLOGY_CONTEXT_MAX_CHARS")
               ontology_profile = OntologyExtractionAdapter.build_selected(
                   manifest,
                   selection.profiles,
                   max_prompt_chars=int(context_limit) if context_limit else None,
               )
               logging.info(
                   "Selected ontology profiles=%s confidence=%.2f reasoning=%s",
                   selection.profiles,
                   selection.confidence,
                   selection.reasoning,
               )
               context_log = Path(os.getenv(
                   "ONTOLOGY_LLM_CONTEXT_LOG",
                   str(Path(__file__).resolve().parents[2] / "logs" / "ontology-llm-context.log"),
               ))
               context_log.parent.mkdir(parents=True, exist_ok=True)
               with context_log.open("a", encoding="utf-8") as log_file:
                   log_file.write(json.dumps({
                       "event": "ontology_profile_selection",
                       "timestamp": datetime.now(timezone.utc).isoformat(),
                       "profiles": selection.profiles,
                       "confidence": selection.confidence,
                       "reasoning": selection.reasoning,
                   }, ensure_ascii=False, indent=2) + "\n\n")
                   log_file.write(json.dumps({
                       "event": "ontology_extraction_context",
                       "timestamp": datetime.now(timezone.utc).isoformat(),
                       "profiles": selection.profiles,
                       "ontology_id": ontology_profile.ontology_id,
                       "transformer_allowed_nodes": list(ontology_profile.allowed_nodes),
                       "transformer_allowed_relationships": list(dict.fromkeys(
                           item if isinstance(item, str) else item[1]
                           for item in ontology_profile.allowed_relationships
                       )),
                       "yaml_context": ontology_profile.yaml_context,
                   }, ensure_ascii=False, indent=2) + "\n\n")
           else:
               ontology_profile = default_profile()
           logging.info("Ontology-guided extraction enabled")

       if ontology_profile:
           # Restrict extraction to the classes and relationship labels from
           # the selected YAML profiles. The raw YAML remains the semantic
           # context, while these lists enforce the extraction boundary.
           allowed_nodes = list(ontology_profile.allowed_nodes)
           allowed_relationships = list(ontology_profile.allowed_relationships)
       else:
           if allowedNodes:
               allowed_nodes = [node.strip() for node in allowedNodes.split(',') if node.strip()]
           else:
               allowed_nodes = []
           allowed_relationships = []
           if allowedRelationship:
               items = [item.strip() for item in allowedRelationship.split(',') if item.strip()]
               if len(items) % 3 != 0:
                   raise LLMGraphBuilderException("allowedRelationship must be a multiple of 3 (source, relationship, target)")
               for i in range(0, len(items), 3):
                   source, relation, target = items[i:i + 3]
                   allowed_relationships.append((source, relation, target))
       logging.info(f"Allowed nodes: {allowed_nodes}")
       if ontology_profile and any(isinstance(item, str) for item in allowed_relationships):
           allowed_relationships = list(dict.fromkeys(
               item if isinstance(item, str) else item[1]
               for item in allowed_relationships
           ))
       for relationship in allowed_relationships:
           if isinstance(relationship, str):
               continue
           source, relation, target = relationship
           if source not in allowed_nodes or target not in allowed_nodes:
               raise LLMGraphBuilderException(
                   f"Invalid relationship ({source}, {relation}, {target}): "
                   f"source or target not in allowedNodes"
               )
       if allowed_relationships:
           # LLMGraphTransformer does not accept a mixed list of endpoint
           # tuples and unconstrained relationship strings. Profile YAMLs
           # can contain both, so use relationship labels consistently when
           # group-rule relationships are present.
           if any(isinstance(item, str) for item in allowed_relationships):
               allowed_relationships = list(dict.fromkeys(
                   item if isinstance(item, str) else item[1]
                   for item in allowed_relationships
               ))
           logging.info(f"Allowed relationships: {allowed_relationships}")
       else:
           logging.info("No allowed relationships provided")

       # Keep document-specific instructions as plain text, and append the
       # structured JSON ontology context generated from the YAML profiles.
       if not ontology_profile:
           raise LLMGraphBuilderException("YAML ontology profile is required for extraction")
       graph_document_list,token_usage = await get_graph_document_list(
           llm,
           combined_chunk_document_list,
           allowed_nodes,
           allowed_relationships,
           callback_handler,
           additional_instructions,
           ontology_profile.node_properties,
           ontology_profile.relationship_properties,
           ontology_profile.yaml_context,
       )
       graph_document_list = rewrite_inverse_relationships(
           graph_document_list, ontology_profile.inverse_relationships
       )
       logging.info(f"Generated {len(graph_document_list)} graph documents")
       if return_envelope:
           from src.ontology_registry import graph_documents_to_envelope
           envelope = graph_documents_to_envelope(
               graph_document_list, model=model_name,
               ontology_id=ontology_profile.ontology_id,
               profile=ontology_profile,
           )
           return graph_document_list, token_usage, envelope
       return graph_document_list, token_usage
   except Exception as e:
       logging.error(f"Error in get_graph_from_llm: {e}", exc_info=True)
       raise LLMGraphBuilderException(f"Error in getting graph from llm: {e}")

def sanitize_additional_instruction(instruction: str) -> str:
   """
   Sanitizes additional instruction by:
   - Replacing curly braces `{}` with `[]` to prevent variable interpretation.
   - Removing potential injection patterns like `os.getenv()`, `eval()`, `exec()`.
   - Stripping problematic special characters.
   - Normalizing whitespace.
   Args:
       instruction (str): Raw additional instruction input.
   Returns:
       str: Sanitized instruction safe for LLM processing.
   """
   logging.info("Sanitizing additional instructions")
   instruction = instruction.replace("{", "[").replace("}", "]")  # Convert `{}` to `[]` for safety
   # Step 2: Block dangerous function calls
   injection_patterns = [r"os\.getenv\(", r"eval\(", r"exec\(", r"subprocess\.", r"import os", r"import subprocess"]
   for pattern in injection_patterns:
       instruction = re.sub(pattern, "[BLOCKED]", instruction, flags=re.IGNORECASE)
   # Step 4: Normalize spaces
   instruction = re.sub(r'\s+', ' ', instruction).strip()
   return instruction
