CREATE TABLE "conversations" (
    "conversation_id" bigserial PRIMARY KEY,
    "user_id" bigint NOT NULL,
    "state" text NOT NULL,
    "status" text NOT NULL DEFAULT 'active',
    "reference_message_id" bigint,
    "data" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
    "finished_at" timestamp with time zone,

    CONSTRAINT "conversations_user_id_fkey"
        FOREIGN KEY ("user_id")
        REFERENCES "users"("user_id")
        ON DELETE CASCADE,

    CONSTRAINT "conversations_reference_message_id_fkey"
        FOREIGN KEY ("reference_message_id")
        REFERENCES "messages"("message_id")
        ON DELETE SET NULL,

    CONSTRAINT "conversations_status_check"
        CHECK ("status" IN ('active', 'finished', 'cancelled'))
);

CREATE INDEX "idx_conversations_user_id"
    ON "conversations" ("user_id");

CREATE INDEX "idx_conversations_reference_message_id"
    ON "conversations" ("reference_message_id");

CREATE INDEX "idx_conversations_status"
    ON "conversations" ("status");

CREATE UNIQUE INDEX "idx_conversations_active_user_id"
    ON "conversations" ("user_id")
    WHERE "status" = 'active';