<template>
  <div>
    <section>
      <h1>Add new note</h1>
      <hr
        class="some-class"
      >
      <br>
      <form @submit.prevent="submit">
        <div class="mb-3">
          <label
            for="title"
            class="form-label"
          >Title:</label>
          <input
            v-model="form.title"
            type="text"
            name="title"
            class="form-control"
          >
        </div>
        <div class="mb-3">
          <label
            for="content"
            class="form-label"
          >Content:</label>
          <textarea
            v-model="form.content"
            name="content"
            class="form-control"
          />
        </div>
        <button
          type="submit"
          class="btn btn-primary"
        >
          Submit
        </button>
      </form>
    </section>
    <br>
    <br>
    <section>
      <h1>Notes</h1>
      <hr
        class="some-class"
      >
      <br>
      <div v-if="notes.length">
        <div
          v-for="note in notes"
          :key="note.id"
          class="notes"
        >
          <div
            class="card"
            style="width: 18rem"
          >
            <div class="card-body">
              <ul>
                <li><strong>Note Title:</strong> {{ note.title }}</li>
                <li><strong>Author:</strong> {{ note.author.username }}</li>
                <li>View</li>
              </ul>
            </div>
          </div>
          <br>
        </div>
      </div>
      <div v-else>
        <p>Nothing to see. Check back later.</p>
      </div>
    </section>
  </div>
</template>

<script>
  import { mapGetters, mapActions } from "vuex";
  export default {
    name: "DashboardItem",
    data() {
      return {
        form: {
          title: "",
          content: "",
        },
      };
    },
    computed: {
      ...mapGetters({ notes: "stateNotes" }),
    },
    watch: {
      form: {
        handler(newForm) {
          if (newForm.title === '' && newForm.content === '') {
            this.form = {
              title: '',
              content: '',
            }
          }
        },
        deep: true,
      },
    },     
    created: function () {
      return this.$store.dispatch("getNotes");
    },
    methods: {
      ...mapActions(["createNote"]),
      async submit() {
        try {
          await this.createNote(this.form);
        } catch (error) {
          console.error(error);
        }
      },
    },
  };
</script>
