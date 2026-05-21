-- internal-ai-search baseline schema (DDL only, no data, no comments).
-- Applied once on empty DB by scripts/apply_migrations.py.

--
-- PostgreSQL database dump
--

\restrict iRd4acNj6bFEtEm7gslKUmAue5TkLG2fJP8rocASmyp1dgzQq0Oemwi4nOSdRmA

-- Dumped from database version 18.3 (Debian 18.3-1.pgdg13+1)
-- Dumped by pg_dump version 18.4 (Debian 18.4-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: action_result; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.action_result AS ENUM (
    'SUCCESS',
    'FAIL'
);


--
-- Name: analysis_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.analysis_status AS ENUM (
    'PENDING',
    'PROCESSING',
    'COMPLETED',
    'FAILED',
    'SKIPPED',
    'DELETED'
);


--
-- Name: data_source_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.data_source_type AS ENUM (
    'OWNCLOUD',
    'NEXTCLOUD',
    'GENERIC_WEBDAV',
    'LOCAL_FOLDER'
);


--
-- Name: scan_job_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.scan_job_status AS ENUM (
    'PENDING',
    'RUNNING',
    'COMPLETED',
    'FAILED',
    'STOPPED',
    'CANCELLING',
    'CANCELLED',
    'PARTIAL'
);


--
-- Name: scan_job_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.scan_job_type AS ENUM (
    'FULL_SCAN',
    'INCREMENTAL_SCAN',
    'MANUAL_SCAN',
    'SCHEDULED_SCAN',
    'WEBDAV_SYNC_ROOT',
    'WEBDAV_SYNC_TREE',
    'PROCESS_PENDING_TEXT',
    'PROCESS_PENDING_DOCUMENTS',
    'CHUNK_COMPLETED_TEXT',
    'EMBED_PENDING_CHUNKS',
    'PIPELINE'
);


--
-- Name: user_role; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.user_role AS ENUM (
    'USER',
    'ADMIN'
);


--
-- Name: user_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.user_status AS ENUM (
    'PENDING',
    'ACTIVE',
    'INACTIVE',
    'LOCKED'
);


--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: action_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.action_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    action_type character varying(100) NOT NULL,
    result public.action_result DEFAULT 'SUCCESS'::public.action_result NOT NULL,
    request_url text,
    request_method character varying(20),
    search_query text,
    data_source_id uuid,
    target_file_id uuid,
    target_file_path text,
    ip_address character varying(100),
    user_agent text,
    detail jsonb,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: app_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.app_users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    login_id character varying(100) NOT NULL,
    password_hash text NOT NULL,
    name character varying(100) NOT NULL,
    email character varying(255),
    department character varying(100),
    role public.user_role DEFAULT 'USER'::public.user_role NOT NULL,
    status public.user_status DEFAULT 'PENDING'::public.user_status NOT NULL,
    must_change_password boolean DEFAULT false NOT NULL,
    failed_login_count integer DEFAULT 0 NOT NULL,
    locked_until timestamp with time zone,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: data_sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.data_sources (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(200) NOT NULL,
    source_type public.data_source_type DEFAULT 'GENERIC_WEBDAV'::public.data_source_type NOT NULL,
    server_url text NOT NULL,
    webdav_root_path text NOT NULL,
    username character varying(255),
    credential_secret_enc text,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    last_connection_test_at timestamp with time zone,
    last_connection_success boolean,
    last_connection_message text,
    last_scan_at timestamp with time zone,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: document_chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_chunks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    data_source_id uuid NOT NULL,
    file_id uuid NOT NULL,
    embedding_model_id uuid,
    embedding_model_name character varying(200) DEFAULT 'BAAI/bge-m3'::character varying NOT NULL,
    chunk_index integer NOT NULL,
    chunk_text text NOT NULL,
    start_line integer,
    end_line integer,
    page_number integer,
    section_title text,
    embedding public.vector(1024),
    token_count integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: duplicate_file_group_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.duplicate_file_group_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    group_id uuid NOT NULL,
    file_id uuid NOT NULL,
    similarity_score numeric(5,4),
    is_latest_candidate boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: duplicate_file_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.duplicate_file_groups (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    data_source_id uuid,
    group_type character varying(50) NOT NULL,
    group_key text NOT NULL,
    file_count integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: embedding_models; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.embedding_models (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    model_name character varying(200) NOT NULL,
    dimension integer NOT NULL,
    max_tokens integer,
    provider character varying(100) DEFAULT 'local'::character varying NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: exclusion_policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.exclusion_policies (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    data_source_id uuid,
    policy_type character varying(50) NOT NULL,
    pattern text NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: file_contents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.file_contents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    file_id uuid NOT NULL,
    data_source_id uuid NOT NULL,
    extracted_text text,
    text_length integer,
    parser_name character varying(100),
    parser_version character varying(50),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.files (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    data_source_id uuid NOT NULL,
    remote_path text NOT NULL,
    filename character varying(500) NOT NULL,
    extension character varying(50),
    is_directory boolean DEFAULT false NOT NULL,
    size_bytes bigint,
    etag character varying(500),
    last_modified timestamp with time zone,
    content_hash character varying(128),
    mime_type character varying(255),
    analysis_status public.analysis_status DEFAULT 'PENDING'::public.analysis_status NOT NULL,
    analysis_error_code character varying(100),
    analysis_error_message text,
    last_indexed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: scan_failures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scan_failures (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    scan_job_id uuid,
    data_source_id uuid NOT NULL,
    file_id uuid,
    remote_path text NOT NULL,
    filename character varying(500),
    extension character varying(50),
    error_code character varying(100) NOT NULL,
    error_message text,
    retry_count integer DEFAULT 0 NOT NULL,
    last_retry_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: scan_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scan_jobs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    data_source_id uuid,
    job_type public.scan_job_type NOT NULL,
    status public.scan_job_status DEFAULT 'PENDING'::public.scan_job_status NOT NULL,
    total_files integer DEFAULT 0 NOT NULL,
    processed_files integer DEFAULT 0 NOT NULL,
    completed_files integer DEFAULT 0 NOT NULL,
    failed_files integer DEFAULT 0 NOT NULL,
    skipped_files integer DEFAULT 0 NOT NULL,
    deleted_files integer DEFAULT 0 NOT NULL,
    current_file_path text,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    requested_by uuid,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    job_params jsonb,
    cancel_requested boolean DEFAULT false NOT NULL,
    worker_id character varying(100),
    heartbeat_at timestamp with time zone,
    parent_job_id uuid,
    pipeline_step character varying(50),
    retry_count integer DEFAULT 0 NOT NULL,
    max_retries integer DEFAULT 1 NOT NULL,
    priority integer DEFAULT 0 NOT NULL
);


--
-- Name: user_favorites; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_favorites (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    file_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: user_recent_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_recent_files (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    file_id uuid NOT NULL,
    viewed_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: user_recent_searches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_recent_searches (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    search_query text NOT NULL,
    data_source_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: action_logs action_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_pkey PRIMARY KEY (id);


--
-- Name: app_users app_users_login_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_users
    ADD CONSTRAINT app_users_login_id_key UNIQUE (login_id);


--
-- Name: app_users app_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_users
    ADD CONSTRAINT app_users_pkey PRIMARY KEY (id);


--
-- Name: data_sources data_sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_sources
    ADD CONSTRAINT data_sources_pkey PRIMARY KEY (id);


--
-- Name: document_chunks document_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT document_chunks_pkey PRIMARY KEY (id);


--
-- Name: duplicate_file_group_items duplicate_file_group_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.duplicate_file_group_items
    ADD CONSTRAINT duplicate_file_group_items_pkey PRIMARY KEY (id);


--
-- Name: duplicate_file_groups duplicate_file_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.duplicate_file_groups
    ADD CONSTRAINT duplicate_file_groups_pkey PRIMARY KEY (id);


--
-- Name: embedding_models embedding_models_model_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_models
    ADD CONSTRAINT embedding_models_model_name_key UNIQUE (model_name);


--
-- Name: embedding_models embedding_models_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.embedding_models
    ADD CONSTRAINT embedding_models_pkey PRIMARY KEY (id);


--
-- Name: exclusion_policies exclusion_policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exclusion_policies
    ADD CONSTRAINT exclusion_policies_pkey PRIMARY KEY (id);


--
-- Name: file_contents file_contents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_contents
    ADD CONSTRAINT file_contents_pkey PRIMARY KEY (id);


--
-- Name: files files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_pkey PRIMARY KEY (id);


--
-- Name: scan_failures scan_failures_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_failures
    ADD CONSTRAINT scan_failures_pkey PRIMARY KEY (id);


--
-- Name: scan_jobs scan_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_jobs
    ADD CONSTRAINT scan_jobs_pkey PRIMARY KEY (id);


--
-- Name: data_sources uq_data_sources_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_sources
    ADD CONSTRAINT uq_data_sources_name UNIQUE (name);


--
-- Name: document_chunks uq_document_chunks_file_index; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT uq_document_chunks_file_index UNIQUE (file_id, chunk_index);


--
-- Name: duplicate_file_group_items uq_duplicate_file_group_items; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.duplicate_file_group_items
    ADD CONSTRAINT uq_duplicate_file_group_items UNIQUE (group_id, file_id);


--
-- Name: file_contents uq_file_contents_file; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_contents
    ADD CONSTRAINT uq_file_contents_file UNIQUE (file_id);


--
-- Name: files uq_files_source_path; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT uq_files_source_path UNIQUE (data_source_id, remote_path);


--
-- Name: user_favorites uq_user_favorites; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_favorites
    ADD CONSTRAINT uq_user_favorites UNIQUE (user_id, file_id);


--
-- Name: user_recent_files uq_user_recent_files; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_recent_files
    ADD CONSTRAINT uq_user_recent_files UNIQUE (user_id, file_id);


--
-- Name: user_favorites user_favorites_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_favorites
    ADD CONSTRAINT user_favorites_pkey PRIMARY KEY (id);


--
-- Name: user_recent_files user_recent_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_recent_files
    ADD CONSTRAINT user_recent_files_pkey PRIMARY KEY (id);


--
-- Name: user_recent_searches user_recent_searches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_recent_searches
    ADD CONSTRAINT user_recent_searches_pkey PRIMARY KEY (id);


--
-- Name: action_logs_action_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX action_logs_action_type_idx ON public.action_logs USING btree (action_type);


--
-- Name: action_logs_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX action_logs_created_at_idx ON public.action_logs USING btree (created_at DESC);


--
-- Name: action_logs_data_source_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX action_logs_data_source_id_idx ON public.action_logs USING btree (data_source_id);


--
-- Name: action_logs_result_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX action_logs_result_idx ON public.action_logs USING btree (result);


--
-- Name: action_logs_user_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX action_logs_user_id_idx ON public.action_logs USING btree (user_id);


--
-- Name: idx_action_logs_action_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_action_logs_action_type ON public.action_logs USING btree (action_type);


--
-- Name: idx_action_logs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_action_logs_created_at ON public.action_logs USING btree (created_at);


--
-- Name: idx_action_logs_data_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_action_logs_data_source_id ON public.action_logs USING btree (data_source_id);


--
-- Name: idx_action_logs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_action_logs_user_id ON public.action_logs USING btree (user_id);


--
-- Name: idx_app_users_login_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_app_users_login_id ON public.app_users USING btree (login_id);


--
-- Name: idx_app_users_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_app_users_role ON public.app_users USING btree (role);


--
-- Name: idx_app_users_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_app_users_status ON public.app_users USING btree (status);


--
-- Name: idx_data_sources_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_data_sources_is_active ON public.data_sources USING btree (is_active);


--
-- Name: idx_data_sources_source_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_data_sources_source_type ON public.data_sources USING btree (source_type);


--
-- Name: idx_document_chunks_data_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_chunks_data_source_id ON public.document_chunks USING btree (data_source_id);


--
-- Name: idx_document_chunks_embedding_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_chunks_embedding_hnsw ON public.document_chunks USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: idx_document_chunks_embedding_model_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_chunks_embedding_model_id ON public.document_chunks USING btree (embedding_model_id);


--
-- Name: idx_document_chunks_file_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_chunks_file_id ON public.document_chunks USING btree (file_id);


--
-- Name: idx_document_chunks_text_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_chunks_text_trgm ON public.document_chunks USING gin (chunk_text public.gin_trgm_ops);


--
-- Name: idx_duplicate_file_group_items_file_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_duplicate_file_group_items_file_id ON public.duplicate_file_group_items USING btree (file_id);


--
-- Name: idx_duplicate_file_group_items_group_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_duplicate_file_group_items_group_id ON public.duplicate_file_group_items USING btree (group_id);


--
-- Name: idx_duplicate_file_groups_data_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_duplicate_file_groups_data_source_id ON public.duplicate_file_groups USING btree (data_source_id);


--
-- Name: idx_file_contents_data_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_file_contents_data_source_id ON public.file_contents USING btree (data_source_id);


--
-- Name: idx_file_contents_file_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_file_contents_file_id ON public.file_contents USING btree (file_id);


--
-- Name: idx_file_contents_text_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_file_contents_text_trgm ON public.file_contents USING gin (extracted_text public.gin_trgm_ops);


--
-- Name: idx_files_analysis_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_files_analysis_status ON public.files USING btree (analysis_status);


--
-- Name: idx_files_content_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_files_content_hash ON public.files USING btree (content_hash);


--
-- Name: idx_files_data_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_files_data_source_id ON public.files USING btree (data_source_id);


--
-- Name: idx_files_etag; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_files_etag ON public.files USING btree (etag);


--
-- Name: idx_files_extension; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_files_extension ON public.files USING btree (extension);


--
-- Name: idx_files_filename; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_files_filename ON public.files USING btree (filename);


--
-- Name: idx_files_filename_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_files_filename_trgm ON public.files USING gin (filename public.gin_trgm_ops);


--
-- Name: idx_files_last_modified; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_files_last_modified ON public.files USING btree (last_modified);


--
-- Name: idx_files_remote_path; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_files_remote_path ON public.files USING btree (remote_path);


--
-- Name: idx_files_remote_path_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_files_remote_path_trgm ON public.files USING gin (remote_path public.gin_trgm_ops);


--
-- Name: idx_scan_failures_data_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scan_failures_data_source_id ON public.scan_failures USING btree (data_source_id);


--
-- Name: idx_scan_failures_error_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scan_failures_error_code ON public.scan_failures USING btree (error_code);


--
-- Name: idx_scan_jobs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scan_jobs_created_at ON public.scan_jobs USING btree (created_at);


--
-- Name: idx_scan_jobs_data_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scan_jobs_data_source_id ON public.scan_jobs USING btree (data_source_id);


--
-- Name: idx_scan_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scan_jobs_status ON public.scan_jobs USING btree (status);


--
-- Name: idx_user_favorites_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_favorites_user_id ON public.user_favorites USING btree (user_id);


--
-- Name: idx_user_recent_files_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_recent_files_user_id ON public.user_recent_files USING btree (user_id);


--
-- Name: idx_user_recent_searches_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_recent_searches_user_id ON public.user_recent_searches USING btree (user_id);


--
-- Name: scan_failures_scan_job_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scan_failures_scan_job_idx ON public.scan_failures USING btree (scan_job_id);


--
-- Name: scan_jobs_data_source_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scan_jobs_data_source_status_idx ON public.scan_jobs USING btree (data_source_id, status);


--
-- Name: scan_jobs_heartbeat_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scan_jobs_heartbeat_idx ON public.scan_jobs USING btree (heartbeat_at) WHERE (status = 'RUNNING'::public.scan_job_status);


--
-- Name: scan_jobs_parent_job_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scan_jobs_parent_job_idx ON public.scan_jobs USING btree (parent_job_id);


--
-- Name: scan_jobs_requested_by_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scan_jobs_requested_by_created_idx ON public.scan_jobs USING btree (requested_by, created_at DESC);


--
-- Name: scan_jobs_status_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scan_jobs_status_created_idx ON public.scan_jobs USING btree (status, created_at);


--
-- Name: scan_jobs_status_priority_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scan_jobs_status_priority_created_idx ON public.scan_jobs USING btree (status, priority DESC, created_at);


--
-- Name: uq_exclusion_policies_by_source; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_exclusion_policies_by_source ON public.exclusion_policies USING btree (data_source_id, policy_type, pattern) WHERE (data_source_id IS NOT NULL);


--
-- Name: uq_exclusion_policies_global; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_exclusion_policies_global ON public.exclusion_policies USING btree (policy_type, pattern) WHERE (data_source_id IS NULL);


--
-- Name: app_users trg_app_users_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_app_users_updated_at BEFORE UPDATE ON public.app_users FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: data_sources trg_data_sources_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_data_sources_updated_at BEFORE UPDATE ON public.data_sources FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: duplicate_file_groups trg_duplicate_file_groups_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_duplicate_file_groups_updated_at BEFORE UPDATE ON public.duplicate_file_groups FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: embedding_models trg_embedding_models_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_embedding_models_updated_at BEFORE UPDATE ON public.embedding_models FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: exclusion_policies trg_exclusion_policies_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_exclusion_policies_updated_at BEFORE UPDATE ON public.exclusion_policies FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: file_contents trg_file_contents_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_file_contents_updated_at BEFORE UPDATE ON public.file_contents FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: files trg_files_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_files_updated_at BEFORE UPDATE ON public.files FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: scan_jobs trg_scan_jobs_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_scan_jobs_updated_at BEFORE UPDATE ON public.scan_jobs FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: action_logs action_logs_data_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_data_source_id_fkey FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE SET NULL;


--
-- Name: action_logs action_logs_target_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_target_file_id_fkey FOREIGN KEY (target_file_id) REFERENCES public.files(id) ON DELETE SET NULL;


--
-- Name: action_logs action_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_logs
    ADD CONSTRAINT action_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.app_users(id) ON DELETE SET NULL;


--
-- Name: data_sources data_sources_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_sources
    ADD CONSTRAINT data_sources_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.app_users(id) ON DELETE SET NULL;


--
-- Name: document_chunks document_chunks_data_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT document_chunks_data_source_id_fkey FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;


--
-- Name: document_chunks document_chunks_embedding_model_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT document_chunks_embedding_model_id_fkey FOREIGN KEY (embedding_model_id) REFERENCES public.embedding_models(id) ON DELETE SET NULL;


--
-- Name: document_chunks document_chunks_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_chunks
    ADD CONSTRAINT document_chunks_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- Name: duplicate_file_group_items duplicate_file_group_items_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.duplicate_file_group_items
    ADD CONSTRAINT duplicate_file_group_items_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- Name: duplicate_file_group_items duplicate_file_group_items_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.duplicate_file_group_items
    ADD CONSTRAINT duplicate_file_group_items_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.duplicate_file_groups(id) ON DELETE CASCADE;


--
-- Name: duplicate_file_groups duplicate_file_groups_data_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.duplicate_file_groups
    ADD CONSTRAINT duplicate_file_groups_data_source_id_fkey FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;


--
-- Name: exclusion_policies exclusion_policies_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exclusion_policies
    ADD CONSTRAINT exclusion_policies_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.app_users(id) ON DELETE SET NULL;


--
-- Name: exclusion_policies exclusion_policies_data_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exclusion_policies
    ADD CONSTRAINT exclusion_policies_data_source_id_fkey FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;


--
-- Name: file_contents file_contents_data_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_contents
    ADD CONSTRAINT file_contents_data_source_id_fkey FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;


--
-- Name: file_contents file_contents_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_contents
    ADD CONSTRAINT file_contents_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- Name: files files_data_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.files
    ADD CONSTRAINT files_data_source_id_fkey FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;


--
-- Name: scan_failures scan_failures_data_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_failures
    ADD CONSTRAINT scan_failures_data_source_id_fkey FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;


--
-- Name: scan_failures scan_failures_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_failures
    ADD CONSTRAINT scan_failures_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- Name: scan_failures scan_failures_scan_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_failures
    ADD CONSTRAINT scan_failures_scan_job_id_fkey FOREIGN KEY (scan_job_id) REFERENCES public.scan_jobs(id) ON DELETE CASCADE;


--
-- Name: scan_jobs scan_jobs_data_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_jobs
    ADD CONSTRAINT scan_jobs_data_source_id_fkey FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE SET NULL;


--
-- Name: scan_jobs scan_jobs_requested_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_jobs
    ADD CONSTRAINT scan_jobs_requested_by_fkey FOREIGN KEY (requested_by) REFERENCES public.app_users(id) ON DELETE SET NULL;


--
-- Name: user_favorites user_favorites_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_favorites
    ADD CONSTRAINT user_favorites_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- Name: user_favorites user_favorites_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_favorites
    ADD CONSTRAINT user_favorites_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.app_users(id) ON DELETE CASCADE;


--
-- Name: user_recent_files user_recent_files_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_recent_files
    ADD CONSTRAINT user_recent_files_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.files(id) ON DELETE CASCADE;


--
-- Name: user_recent_files user_recent_files_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_recent_files
    ADD CONSTRAINT user_recent_files_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.app_users(id) ON DELETE CASCADE;


--
-- Name: user_recent_searches user_recent_searches_data_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_recent_searches
    ADD CONSTRAINT user_recent_searches_data_source_id_fkey FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE SET NULL;


--
-- Name: user_recent_searches user_recent_searches_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_recent_searches
    ADD CONSTRAINT user_recent_searches_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.app_users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict iRd4acNj6bFEtEm7gslKUmAue5TkLG2fJP8rocASmyp1dgzQq0Oemwi4nOSdRmA

