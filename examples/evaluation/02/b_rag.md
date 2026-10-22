Retrieval: I implemented RAG retrieval with document citations and tested retrieval against a fixed set of questions.
Augmentation: I inserted the retrieved passages into the LLM prompt as context.
Generation: I called the LLM with that context to produce answers with citations to the retrieved documents.
