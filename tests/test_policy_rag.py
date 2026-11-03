import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from hrms.policy_rag import OpenAIPolicyRAG


class FakeOpenAIClient:
    def __init__(self):
        self.embedding_batches = []
        self.chat_messages = None
        self.embeddings = SimpleNamespace(create=self.create_embeddings)
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self.create_chat_completion)
        )

    def create_embeddings(self, model, input):
        self.embedding_batches.append((model, input))
        data = [
            SimpleNamespace(index=index, embedding=self.vector_for(text))
            for index, text in enumerate(input)
        ]
        return SimpleNamespace(data=data)

    @staticmethod
    def vector_for(text):
        terms = text.casefold()
        labels = ("leave", "equipment", "ticket", "password", "meeting", "expense", "onboard")
        return [1.0 if label in terms else 0.0 for label in labels]

    def create_chat_completion(self, model, temperature, messages):
        self.chat_messages = messages
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Submit the request in the HR system [SYN-LEAVE-001].")
                )
            ]
        )


class OpenAIPolicyRAGTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.client = FakeOpenAIClient()
        self.rag = OpenAIPolicyRAG(
            index_path=Path(self.temp_dir.name) / "policy.sqlite3",
            client=self.client,
            min_relevance_score=0.2,
        )

    def test_semantic_search_builds_and_persists_vector_index(self):
        results = self.rag.search("How do I request annual leave?")

        self.assertTrue(results)
        self.assertEqual(results[0]["doc_id"], "SYN-LEAVE-001")
        self.assertEqual(results[0]["category"], "leave")
        self.assertTrue(Path(self.temp_dir.name, "policy.sqlite3").exists())
        self.assertEqual(len(self.client.embedding_batches), 2)

    def test_answer_uses_retrieved_context_and_returns_citations(self):
        result = self.rag.answer("How do I request annual leave?")

        self.assertIn("[SYN-LEAVE-001]", result["answer"])
        self.assertEqual(result["sources"][0]["doc_id"], "SYN-LEAVE-001")
        self.assertIn("Submit leave dates", self.client.chat_messages[1]["content"])

    def test_unrelated_question_does_not_call_chat_model(self):
        result = self.rag.answer("Tell me about a cosmic nebula.")

        self.assertEqual(result["sources"], [])
        self.assertIn("couldn't find relevant information", result["answer"])
        self.assertIsNone(self.client.chat_messages)

    def test_rebuilds_index_when_dataset_changes(self):
        dataset_path = Path(self.temp_dir.name) / "policies.json"
        dataset_path.write_text(
            json.dumps([{
                "doc_id": "TEST-001",
                "title": "Test Policy",
                "category": "leave",
                "effective_date": "2026-01-01",
                "text": "Submit annual leave through the HR system.",
            }]),
            encoding="utf-8",
        )
        self.rag.dataset_path = dataset_path
        self.assertEqual(self.rag.rebuild_index(), 1)

        dataset_path.write_text(
            json.dumps([{
                "doc_id": "TEST-001",
                "title": "Test Policy",
                "category": "leave",
                "effective_date": "2026-01-01",
                "text": "Submit annual leave through the manager.",
            }]),
            encoding="utf-8",
        )
        self.rag.search("annual leave")

        self.assertEqual(len(self.client.embedding_batches), 3)


if __name__ == "__main__":
    unittest.main()
